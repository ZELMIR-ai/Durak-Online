"""
WebSocket сервер — управление комнатами и игрой
"""
import asyncio
import json
import random
import string
import logging
from typing import Optional
import websockets
from websockets.server import WebSocketServerProtocol

from game import DurakGame, GameState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище: room_id -> DurakGame
rooms: dict[str, DurakGame] = {}
# Хранилище: player_id -> WebSocket
connections: dict[str, WebSocketServerProtocol] = {}
# Хранилище: player_id -> room_id
player_rooms: dict[str, str] = {}
# Очередь матчмейкинга: (player_id, name, mode)
matchmaking_queue: dict[str, list] = {"podkidnoy": [], "perevodnoj": []}


def generate_room_code():
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def broadcast_to_room(room_id: str):
    """Отправить обновлённое состояние всем игрокам в комнате"""
    game = rooms.get(room_id)
    if not game:
        return
    for player in game.players:
        ws = connections.get(player.id)
        if ws:
            try:
                state = game.get_state_for_player(player.id)
                await ws.send(json.dumps({"type": "game_state", "data": state}))
            except Exception as e:
                logger.error(f"Error sending to {player.id}: {e}")


async def send_to_player(player_id: str, msg: dict):
    ws = connections.get(player_id)
    if ws:
        try:
            await ws.send(json.dumps(msg))
        except Exception as e:
            logger.error(f"Error sending to {player_id}: {e}")


async def handle_create_room(ws, data: dict, player_id: str):
    name = data.get("name", "Игрок")
    mode = data.get("mode", "podkidnoy")

    room_id = generate_room_code()
    while room_id in rooms:
        room_id = generate_room_code()

    game = DurakGame(room_id, mode)
    game.add_player(player_id, name)
    rooms[room_id] = game
    player_rooms[player_id] = room_id

    await send_to_player(player_id, {
        "type": "room_created",
        "room_id": room_id,
        "mode": mode,
    })
    await broadcast_to_room(room_id)


async def handle_join_room(ws, data: dict, player_id: str):
    name = data.get("name", "Игрок")
    room_id = data.get("room_id", "").upper().strip()
    game = rooms.get(room_id)

    if not game:
        await send_to_player(player_id, {"type": "error", "message": "Комната не найдена"})
        return
    if game.state != GameState.WAITING:
        await send_to_player(player_id, {"type": "error", "message": "Игра уже началась"})
        return
    if len(game.players) >= 6:
        await send_to_player(player_id, {"type": "error", "message": "Комната заполнена"})
        return

    game.add_player(player_id, name)
    player_rooms[player_id] = room_id

    await send_to_player(player_id, {"type": "room_joined", "room_id": room_id})
    await broadcast_to_room(room_id)


async def handle_matchmaking(ws, data: dict, player_id: str):
    name = data.get("name", "Игрок")
    mode = data.get("mode", "podkidnoy")
    queue = matchmaking_queue[mode]

    # Убрать старую запись игрока из очереди (если есть)
    matchmaking_queue[mode] = [(pid, n) for pid, n in queue if pid != player_id]
    queue = matchmaking_queue[mode]

    queue.append((player_id, name))
    await send_to_player(player_id, {"type": "matchmaking", "status": "searching", "queue_size": len(queue)})

    # Если в очереди >= 2 игрока — создаём комнату
    if len(queue) >= 2:
        p1_id, p1_name = queue.pop(0)
        p2_id, p2_name = queue.pop(0)

        room_id = generate_room_code()
        while room_id in rooms:
            room_id = generate_room_code()

        game = DurakGame(room_id, mode)
        game.add_player(p1_id, p1_name)
        game.add_player(p2_id, p2_name)
        rooms[room_id] = game
        player_rooms[p1_id] = room_id
        player_rooms[p2_id] = room_id

        # Автоматически ставим ready и начинаем
        game.set_ready(p1_id)
        game.set_ready(p2_id)
        game.start_game()

        await send_to_player(p1_id, {"type": "match_found", "room_id": room_id})
        await send_to_player(p2_id, {"type": "match_found", "room_id": room_id})
        await broadcast_to_room(room_id)


async def handle_ready(ws, data: dict, player_id: str):
    room_id = player_rooms.get(player_id)
    game = rooms.get(room_id)
    if not game:
        return

    game.set_ready(player_id)
    await broadcast_to_room(room_id)

    if game.all_ready():
        game.start_game()
        await broadcast_to_room(room_id)


async def handle_action(ws, data: dict, player_id: str):
    room_id = player_rooms.get(player_id)
    game = rooms.get(room_id)
    if not game or game.state != GameState.PLAYING:
        return

    action = data.get("action")
    result = {"ok": False, "error": "Неизвестное действие"}

    if action == "attack":
        result = game.attack(player_id, data.get("card_id"))
    elif action == "defend":
        result = game.defend(player_id, data.get("attack_card_id"), data.get("defense_card_id"))
    elif action == "transfer":
        result = game.transfer(player_id, data.get("card_id"))
    elif action == "take":
        result = game.take_cards(player_id)
    elif action == "end_turn":
        result = game.end_turn(player_id)

    if not result["ok"]:
        await send_to_player(player_id, {"type": "error", "message": result.get("error", "Ошибка")})
    else:
        await broadcast_to_room(room_id)

        # Проверяем финал
        if game.state == GameState.FINISHED:
            loser = next((p for p in rooms.get(room_id, DurakGame("", "")).players
                          if p.id == game.loser_id), None)
            for pid in list(player_rooms.keys()):
                if player_rooms.get(pid) == room_id:
                    await send_to_player(pid, {
                        "type": "game_over",
                        "loser_id": game.loser_id,
                        "loser_name": loser.name if loser else "?",
                        "is_loser": pid == game.loser_id,
                    })


async def handle_leave(player_id: str):
    room_id = player_rooms.pop(player_id, None)
    if not room_id:
        return
    game = rooms.get(room_id)
    if game:
        game.remove_player(player_id)
        if len(game.players) == 0:
            del rooms[room_id]
        else:
            # Уведомляем оставшихся
            for p in game.players:
                await send_to_player(p.id, {
                    "type": "player_left",
                    "player_id": player_id,
                })
            await broadcast_to_room(room_id)


async def handle_connection(ws: WebSocketServerProtocol, path: str):
    player_id = None
    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            # Первым делом — регистрация
            if msg_type == "register":
                player_id = data.get("player_id", f"guest_{id(ws)}")
                connections[player_id] = ws
                logger.info(f"Player connected: {player_id}")
                await send_to_player(player_id, {"type": "registered", "player_id": player_id})
                continue

            if player_id is None:
                continue

            if msg_type == "create_room":
                await handle_create_room(ws, data, player_id)
            elif msg_type == "join_room":
                await handle_join_room(ws, data, player_id)
            elif msg_type == "matchmaking":
                await handle_matchmaking(ws, data, player_id)
            elif msg_type == "ready":
                await handle_ready(ws, data, player_id)
            elif msg_type == "action":
                await handle_action(ws, data, player_id)
            elif msg_type == "leave":
                await handle_leave(player_id)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if player_id:
            connections.pop(player_id, None)
            await handle_leave(player_id)
            logger.info(f"Player disconnected: {player_id}")


async def main():
    host = "0.0.0.0"
    port = 8765
    logger.info(f"WebSocket server starting on ws://{host}:{port}")
    async with websockets.serve(handle_connection, host, port):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
