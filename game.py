"""
Дурак — игровая логика
Поддерживает: подкидной и переводной дурак, 2-6 игроков
"""
import random
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class Suit(str, Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"


class Rank(str, Enum):
    SIX = "6"
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    TEN = "10"
    JACK = "J"
    QUEEN = "Q"
    KING = "K"
    ACE = "A"


RANK_ORDER = [r.value for r in Rank]


@dataclass
class Card:
    suit: Suit
    rank: Rank

    def to_dict(self):
        return {"suit": self.suit.value, "rank": self.rank.value, "id": f"{self.rank.value}{self.suit.value}"}

    def rank_index(self):
        return RANK_ORDER.index(self.rank.value)

    def beats(self, other: "Card", trump: Suit) -> bool:
        """Может ли эта карта побить другую?"""
        if self.suit == other.suit:
            return self.rank_index() > other.rank_index()
        if self.suit == trump and other.suit != trump:
            return True
        return False


@dataclass
class Player:
    id: str
    name: str
    hand: list[Card] = field(default_factory=list)
    is_ready: bool = False
    is_connected: bool = True

    def to_dict(self, hide_cards=True):
        return {
            "id": self.id,
            "name": self.name,
            "card_count": len(self.hand),
            "cards": [c.to_dict() for c in self.hand] if not hide_cards else [],
            "is_ready": self.is_ready,
            "is_connected": self.is_connected,
        }


class GameState(str, Enum):
    WAITING = "waiting"
    PLAYING = "playing"
    ROUND_END = "round_end"
    FINISHED = "finished"


@dataclass
class TableSlot:
    attack_card: Optional[Card] = None
    defense_card: Optional[Card] = None

    def to_dict(self):
        return {
            "attack": self.attack_card.to_dict() if self.attack_card else None,
            "defense": self.defense_card.to_dict() if self.defense_card else None,
        }


class DurakGame:
    def __init__(self, room_id: str, game_mode: str = "podkidnoy"):
        self.room_id = room_id
        self.game_mode = game_mode  # "podkidnoy" or "perevodnoj"
        self.players: list[Player] = []
        self.deck: list[Card] = []
        self.trump_suit: Optional[Suit] = None
        self.trump_card: Optional[Card] = None
        self.table: list[TableSlot] = []
        self.discard: list[Card] = []
        self.state = GameState.WAITING
        self.attacker_idx: int = 0
        self.defender_idx: int = 1
        self.loser_id: Optional[str] = None
        self.turn_count: int = 0

    def add_player(self, player_id: str, name: str) -> bool:
        if len(self.players) >= 6:
            return False
        if any(p.id == player_id for p in self.players):
            return False
        self.players.append(Player(id=player_id, name=name))
        return True

    def remove_player(self, player_id: str):
        self.players = [p for p in self.players if p.id != player_id]

    def set_ready(self, player_id: str):
        for p in self.players:
            if p.id == player_id:
                p.is_ready = True

    def all_ready(self) -> bool:
        return len(self.players) >= 2 and all(p.is_ready for p in self.players)

    def start_game(self):
        self._create_deck()
        self._deal_cards()
        self._determine_first_attacker()
        self.state = GameState.PLAYING
        self.turn_count = 1

    def _create_deck(self):
        self.deck = [Card(suit, rank) for suit in Suit for rank in Rank]
        random.shuffle(self.deck)
        # Последняя карта — козырь
        self.trump_card = self.deck[-1]
        self.trump_suit = self.trump_card.suit

    def _deal_cards(self):
        for player in self.players:
            for _ in range(6):
                if self.deck:
                    player.hand.append(self.deck.pop(0))

    def _determine_first_attacker(self):
        """Первый ходит тот, у кого наименьший козырь"""
        min_trump_idx = None
        min_trump_rank = 999
        for i, player in enumerate(self.players):
            for card in player.hand:
                if card.suit == self.trump_suit:
                    r = card.rank_index()
                    if r < min_trump_rank:
                        min_trump_rank = r
                        min_trump_idx = i
        if min_trump_idx is None:
            min_trump_idx = 0
        self.attacker_idx = min_trump_idx
        self.defender_idx = (min_trump_idx + 1) % len(self.players)

    @property
    def attacker(self) -> Player:
        return self.players[self.attacker_idx]

    @property
    def defender(self) -> Player:
        return self.players[self.defender_idx]

    def get_attackers(self) -> list[Player]:
        """Все игроки, кроме защищающегося, могут подкидывать"""
        return [p for i, p in enumerate(self.players) if i != self.defender_idx]

    def can_attack(self, player_id: str) -> bool:
        return any(p.id == player_id for p in self.get_attackers())

    def attack(self, player_id: str, card_id: str) -> dict:
        """Атака / подкидывание карты"""
        if not self.can_attack(player_id):
            return {"ok": False, "error": "Не ваш ход атаковать"}

        player = next((p for p in self.players if p.id == player_id), None)
        card = next((c for c in player.hand if f"{c.rank.value}{c.suit.value}" == card_id), None)
        if not card:
            return {"ok": False, "error": "Карта не найдена"}

        # Можно подкидывать только карты, чьи достоинства уже есть на столе
        if self.table:
            table_ranks = set()
            for slot in self.table:
                if slot.attack_card:
                    table_ranks.add(slot.attack_card.rank.value)
                if slot.defense_card:
                    table_ranks.add(slot.defense_card.rank.value)
            if card.rank.value not in table_ranks:
                return {"ok": False, "error": "Можно подкидывать только карты такого же достоинства"}

        # Нельзя класть больше карт, чем у защищающегося
        open_slots = sum(1 for s in self.table if s.defense_card is None)
        if not self.table or open_slots == 0:
            # Первый ход — просто кладём
            pass
        
        if len(self.table) >= len(self.defender.hand) and self.table:
            return {"ok": False, "error": "Нельзя подкидывать больше карт, чем есть у защищающегося"}

        player.hand.remove(card)
        self.table.append(TableSlot(attack_card=card))
        return {"ok": True, "event": "attack", "card": card.to_dict()}

    def defend(self, player_id: str, attack_card_id: str, defense_card_id: str) -> dict:
        """Защита — отбить конкретную карту атаки"""
        if self.defender.id != player_id:
            return {"ok": False, "error": "Вы не защищаетесь"}

        # Найти слот с картой атаки
        slot = next((s for s in self.table
                     if s.attack_card and f"{s.attack_card.rank.value}{s.attack_card.suit.value}" == attack_card_id
                     and s.defense_card is None), None)
        if not slot:
            return {"ok": False, "error": "Такой карты атаки нет или она уже отбита"}

        def_card = next((c for c in self.defender.hand
                         if f"{c.rank.value}{c.suit.value}" == defense_card_id), None)
        if not def_card:
            return {"ok": False, "error": "Карта не найдена в руке"}

        if not def_card.beats(slot.attack_card, self.trump_suit):
            return {"ok": False, "error": "Этой картой нельзя отбить"}

        self.defender.hand.remove(def_card)
        slot.defense_card = def_card
        return {"ok": True, "event": "defend"}

    def transfer(self, player_id: str, card_id: str) -> dict:
        """Перевод (только в переводном дураке)"""
        if self.game_mode != "perevodnoj":
            return {"ok": False, "error": "Перевод доступен только в переводном дураке"}
        if self.defender.id != player_id:
            return {"ok": False, "error": "Вы не защищаетесь"}
        if len(self.table) > 1:
            return {"ok": False, "error": "Перевод возможен только при одной карте атаки"}
        if not self.table or self.table[0].defense_card:
            return {"ok": False, "error": "Нечего переводить"}

        card = next((c for c in self.defender.hand if f"{c.rank.value}{c.suit.value}" == card_id), None)
        if not card:
            return {"ok": False, "error": "Карта не найдена"}

        if card.rank != self.table[0].attack_card.rank:
            return {"ok": False, "error": "Перевод только картой того же достоинства"}

        # Следующий игрок должен иметь достаточно карт
        next_defender_idx = (self.defender_idx + 1) % len(self.players)
        next_defender = self.players[next_defender_idx]
        if len(next_defender.hand) < len(self.table) + 1:
            return {"ok": False, "error": "У следующего игрока недостаточно карт для приёма перевода"}

        self.defender.hand.remove(card)
        self.table.append(TableSlot(attack_card=card))

        # Переносим роли
        self.attacker_idx = self.defender_idx
        self.defender_idx = next_defender_idx

        return {"ok": True, "event": "transfer", "new_defender": self.defender.id}

    def take_cards(self, player_id: str) -> dict:
        """Защищающийся берёт все карты со стола"""
        if self.defender.id != player_id:
            return {"ok": False, "error": "Только защищающийся может взять карты"}

        for slot in self.table:
            if slot.attack_card:
                self.defender.hand.append(slot.attack_card)
            if slot.defense_card:
                self.defender.hand.append(slot.defense_card)
        self.table.clear()

        # Добираем карты (атакующий и подкидывавшие, но не защищавшийся)
        self._refill_hands(skip_player=self.defender.id)

        # Следующий ход — следующий после защищавшегося
        self.attacker_idx = (self.defender_idx + 1) % len(self.players)
        self.defender_idx = (self.attacker_idx + 1) % len(self.players)

        self._check_winners()
        return {"ok": True, "event": "take"}

    def end_turn(self, player_id: str) -> dict:
        """Атакующий завершает ход (все карты отбиты)"""
        if self.attacker.id != player_id:
            return {"ok": False, "error": "Только атакующий может завершить ход"}

        # Проверить что все карты отбиты
        if any(s.defense_card is None for s in self.table):
            return {"ok": False, "error": "Не все карты отбиты"}

        # Сбрасываем карты
        for slot in self.table:
            self.discard.extend([slot.attack_card, slot.defense_card])
        self.table.clear()

        # Добираем карты
        self._refill_hands()

        # Следующий ход
        self.attacker_idx = self.defender_idx % len(self.players)
        self.defender_idx = (self.attacker_idx + 1) % len(self.players)
        self.turn_count += 1

        self._check_winners()
        return {"ok": True, "event": "end_turn"}

    def _refill_hands(self, skip_player: Optional[str] = None):
        """Добор карт из колоды до 6"""
        order = list(range(len(self.players)))
        # Порядок: сначала атакующий
        order = order[self.attacker_idx:] + order[:self.attacker_idx]
        for i in order:
            p = self.players[i]
            if skip_player and p.id == skip_player:
                continue
            while len(p.hand) < 6 and self.deck:
                p.hand.append(self.deck.pop(0))

    def _check_winners(self):
        """Проверяем, кто вышел из игры (нет карт и колода пуста)"""
        if not self.deck:
            # Убираем игроков без карт
            finished = [p for p in self.players if len(p.hand) == 0]
            for p in finished:
                self.players.remove(p)

            if len(self.players) == 1:
                self.loser_id = self.players[0].id
                self.state = GameState.FINISHED
            elif len(self.players) == 0:
                self.state = GameState.FINISHED

            # Пересчитываем индексы
            if self.state == GameState.PLAYING and len(self.players) > 1:
                self.attacker_idx = self.attacker_idx % len(self.players)
                self.defender_idx = (self.attacker_idx + 1) % len(self.players)

    def get_state_for_player(self, player_id: str) -> dict:
        """Полное состояние игры для конкретного игрока"""
        player = next((p for p in self.players if p.id == player_id), None)
        return {
            "room_id": self.room_id,
            "game_mode": self.game_mode,
            "state": self.state.value,
            "trump": self.trump_suit.value if self.trump_suit else None,
            "trump_card": self.trump_card.to_dict() if self.trump_card else None,
            "deck_count": len(self.deck),
            "table": [slot.to_dict() for slot in self.table],
            "discard_count": len(self.discard),
            "players": [p.to_dict(hide_cards=(p.id != player_id)) for p in self.players],
            "my_hand": [c.to_dict() for c in player.hand] if player else [],
            "attacker_id": self.attacker.id if self.players else None,
            "defender_id": self.defender.id if len(self.players) > 1 else None,
            "my_id": player_id,
            "loser_id": self.loser_id,
            "turn_count": self.turn_count,
            "can_attack": self.can_attack(player_id),
            "is_defender": self.defender.id == player_id if len(self.players) > 1 else False,
        }
