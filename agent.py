import time
from extension.board_utils import list_legal_moves_for, copy_piece_move, take_notes
from extension.board_rules import only_2kings, cannot_move
from chessmaker.chess.base import Board, Player, Piece, MoveOption
from chessmaker.chess.pieces import King
from typing import Iterable

type Move = tuple[Piece, MoveOption]

# == DEBUGGING ==
print_once_last_message: str = ""
print_once_count: int = 0

def print_once(msg: str):
    global print_once_last_message, print_once_count
    """Print a message if it is not the same as the last printed message."""

    if msg != print_once_last_message:
        if print_once_count > 0:
            if print_once_count > 1:
                print(f" x{print_once_count}")
            print()

        print(msg, end="")
        print_once_last_message = msg
        print_once_count = 1
    else:
        print_once_count += 1


# == ZOBRIST HASHING ==
import random
ZobristTable = list[list[list[int]]]

def piece_index(piece: str, color: str) -> int:
    if piece == "Pawn":
        id = 0
    elif piece == "Knight":
        id = 1
    elif piece == "Right":
        id = 2
    elif piece == "King":
        id = 3
    elif piece == "Bishop":
        id = 4
    else: # p == "Queen"
        id = 5

    if color == "white":
        return id
    else: # c == "black"
        return id + 6


def random_int() -> int:
    min = 0
    max = pow(2, 64)
    return random.randint(min, max)


def init_zobrist() -> tuple[ZobristTable, int]:
    zobrist_table = [[[random_int() for _ in range(12)] for _ in range(5)] for _ in range(5)]
    zobrist_black_to_move = random_int() # Add this
    return zobrist_table, zobrist_black_to_move


def compute_hash(board: Board, zobrist_table: ZobristTable, zobrist_black_to_move: int) -> int:
    h = 0
    pieces: list[Piece] = board.get_pieces()                # type: ignore[attr-defined]
    for piece in pieces:
        index = piece_index(piece.name, piece.player.name)  # type: ignore[attr-defined]
        position = piece.position                           # type: ignore[attr-defined]
        h ^= zobrist_table[position[0]][position[1]][index]
    if board.current_player.name == "black":                # type: ignore[attr-defined]
        h ^= zobrist_black_to_move
    return h


def update_hash(current_hash: int, piece: Piece, move_og: MoveOption, captured_piece: Piece | None, zobrist_table: ZobristTable, zobrist_black_to_move: int) -> int:
    capturer_index = piece_index(piece.name, piece.player.name)                                               # type: ignore[attr-defined]
    captured_index = piece_index(captured_piece.name, captured_piece.player.name) if captured_piece else None # type: ignore[attr-defined]

    # XOR out the piece from its old square
    current_hash ^= zobrist_table[piece.position.x][piece.position.y][capturer_index] # type: ignore[attr-defined]

    # XOR out the captured piece (if any)
    if captured_piece:
        current_hash ^= zobrist_table[captured_piece.position.x][captured_piece.position.y][captured_index] # type: ignore[attr-defined]

    # XOR in the piece at its new square
    current_hash ^= zobrist_table[move_og.position.x][move_og.position.y][capturer_index]

    # XOR the side to move
    current_hash ^= zobrist_black_to_move

    return current_hash


(zobrist_table, zobrist_black_to_move) = init_zobrist()


# == UNDOER ==
# Assuming these imports are already present in your environment based on the previous context
from typing import Any
from chessmaker.chess.pieces import Pawn


def make_move(board: Board, piece: Piece, move_option: MoveOption) -> dict[str, Any]:
    """Makes a move on the board and returns undo information."""
    undo_info = {
        'piece': piece,
        'from_position': piece.position,                                       # type: ignore[attr-defined]
        'to_position': move_option.position,
        'captured_piece': get_captured_piece(board, move_option)
    }

    # if pawn log 
    if isinstance(piece, Pawn):
        undo_info['_moved_turns_ago'] = piece._moved_turns_ago                 # type: ignore[attr-defined]
        undo_info['_last_position'] = piece._last_position                     # type: ignore[attr-defined]
        undo_info['en_passant'] = move_option.extra.get('en_passant', False)
        undo_info['direction'] = piece._direction.value                        # type: ignore[attr-defined]

    # Move the piece
    piece.move(move_option)                                                    # type: ignore[attr-defined]

    return undo_info


def undo_move(board: Board, undo_info: dict[str, Any]):
    piece = undo_info['piece']
    from_position = undo_info['from_position']
    to_position = undo_info['to_position']
    captured_piece = undo_info['captured_piece']
    en_passant = undo_info.get('en_passant', False)

    from_square = board.__getitem__(from_position)                                                     # type: ignore[attr-defined]
    to_square = board.__getitem__(to_position)                                                         # type: ignore[attr-defined]
    if en_passant:
        # Remove the pawn that captured en passant
        to_square.piece = None                                                                         # type: ignore[attr-defined]
        # Adjust pawn to one further in `direction` as it had originally moved 2 squares
        to_square = board.__getitem__(Position(to_position.x, to_position.y - undo_info['direction'])) # type: ignore[attr-defined]

    from_square.piece = piece                                                                          # type: ignore[attr-defined]

    if captured_piece:
        to_square.piece = captured_piece                                                               # type: ignore[attr-defined]
    else:
        to_square.piece = None                                                                         # type: ignore[attr-defined]

    if isinstance(piece, Pawn):
        piece._moved_turns_ago = undo_info['_moved_turns_ago']                                         # type: ignore[attr-defined]
        piece._last_position = undo_info['_last_position']                                             # type: ignore[attr-defined]


    board.current_player = next(board.turn_iterator)                                                   # type: ignore[attr-defined]
    # board.current_player = piece.player


# == BOARD STATE ==

repetition_history = {}


def update_repetition_count(hashed_board: int) -> None:
    if hashed_board in repetition_history:
        repetition_history[hashed_board] += 1
    else:
        repetition_history[hashed_board] = 1


def undo_repetition_count(hashed_board: int) -> None:
    if hashed_board in repetition_history:
        repetition_history[hashed_board] -= 1
        if repetition_history[hashed_board] <= 0:
            del repetition_history[hashed_board]


def current_player_is_in_check(board: Board) -> bool:
    current_player: Player = board.current_player # type: ignore[attr-defined]
    player_pieces: Iterable[Piece] = board.get_player_pieces(current_player) # type: ignore[attr-defined]
    king : King = next(piece for piece in player_pieces if isinstance(piece, King))
    is_attacked = king.is_attacked() # type: ignore[attr-defined]
    return is_attacked


def clone_board(board: Board) -> Board:
    board_clone: Board = board.clone()  # type: ignore[attr-defined]
    if hasattr(board, "_rep_hist"):
        board_clone._rep_hist = dict(board._rep_hist)  # type: ignore[attr-defined]
    return board_clone


def get_captured_piece(board: Board, move_opt: MoveOption) -> Piece | None:
    if move_opt.captures:
        captured_position = next(iter(move_opt.captures))
        captured_square = board.__getitem__(captured_position) # type: ignore[attr-defined]
        captured_piece = captured_square.piece                 # type: ignore[attr-defined]
        return captured_piece
    return None


# == EVALUATION ==

def piece_value(piece: Piece) -> int:
    """
    Returns the value of a piece based on its type.
    """
    piece_name: str = piece.name # type: ignore[attr-defined]

    if piece_name == "Pawn":
        return 1
    elif piece_name == "Knight":
        return 3
    elif piece_name == "Bishop":
        return 3
    elif piece_name == "Rook":
        return 5
    elif piece_name == "Right":
        return 7
    elif piece_name == "Queen":
        return 9
    elif piece_name == "King":
        return 0
    return 0


def evaluate_board(board: Board):
    """
    A simple evaluation function for the board.
    This function should return a numerical value representing the desirability of the board state for the current player.
    Positive values favor the current player, negative values favor the opponent.

    Parameters
    ----------
    board: the current chess board
    player: the current player

    Returns
    -------
    score: numerical evaluation of the board state
    """
    
    score = 0
    current_player: Player = board.current_player  # type: ignore[attr-defined]
    pieces: Iterable[Piece] = board.get_pieces()   # type: ignore[attr-defined]

    for piece in pieces:
        value = piece_value(piece)
        piece_player: Player = piece.player        # type: ignore[attr-defined]
        if piece_player == current_player:
            score += value
        else:
            score -= value
    return score


def move_is_check(board: Board, piece: Piece, move_opt: MoveOption) -> bool:
    board_clone = clone_board(board)
    _, new_piece, new_move_opt = copy_piece_move(board_clone, piece, move_opt) # type: ignore[attr-defined]
    new_piece.move(new_move_opt)                                               # type: ignore[attr-defined]
    return current_player_is_in_check(board_clone)


def sort_key(board: Board, piece: Piece, move_opt: MoveOption, memo_move: Move | None) -> int:
    score = 0
    
    # check if is check:
    #if move_is_check(board, piece, move_opt):
    #    score += 1000

    # What we previously computed to be best, even at a lower depth, is probably still best
    if (piece, move_opt) == memo_move:
        return 2000

    # Most Valuable Victim - Least Valuable Aggressor
    captured_piece = get_captured_piece(board, move_opt)
    if captured_piece:
        captured_value = piece_value(captured_piece)
        attacker_value = piece_value(piece)
        score += 1000 + captured_value * 10 - attacker_value

    # Promotion
    if hasattr(move_opt, 'promote'):
        score += 900
    
    return score


# == NEGAMAX WITH ALPHA-BETA PRUNING ==

memo: dict[int, tuple[float, Move | None, int]] = {}

def negamax(board: Board, depth: int, alpha: float, beta: float, start_time: float, time_limit: float, board_hash: int) -> tuple[float, Move | None, bool]:
    """
    Negamax search algorithm with alpha-beta pruning and time management.

    Parameters
    ----------
    board: the current chess board
    player: the current player
    depth: current depth in the search tree
    alpha: alpha value for pruning
    beta: beta value for pruning
    start_time: time when the search started
    time_limit: maximum allowed time for the search

    Returns
    -------
    best_value: the best evaluation value found
    best_move: the best move found
    time_exceeded: whether the time limit was exceeded
    """
    
    if time.perf_counter() - start_time > time_limit:
        print_once("Time limit exceeded during search")
        return 0, None, True
    
    if repetition_history[board_hash] >= 5:
        return 0, None, False

    (memo_value, memo_move) = (None, None)
    if board_hash in memo:
        (memo_value, memo_move, memo_depth) = memo[board_hash]
        if memo_depth >= depth:
            return memo_value, memo_move, False

    if depth <= 0:
        return evaluate_board(board), None, False
    
    if only_2kings(board): # draw
        return 0, None, False

    if cannot_move(board): # loss for current player
        return -100_000 - depth, None, False

    player = board.current_player # type: ignore[attr-defined] (pylance is DUMBFOUNDINGLY stupid sometimes (all the time))
    best_value = float('-inf')
    best_move = None
    time_exceeded = False
    first_move = True

    moves: list[Move] = list_legal_moves_for(board, player)
    moves.sort(key = lambda move: sort_key(board, move[0], move[1], memo_move), reverse=True)
    for piece, move_opt in moves:
        # new_piece: Piece; new_move_opt: MoveOption; new_board: Board
        captured_piece: Piece | None = get_captured_piece(board, move_opt)
        new_board_hash = update_hash(board_hash, piece, move_opt, captured_piece, zobrist_table, zobrist_black_to_move)
        update_repetition_count(new_board_hash)
        info = make_move(board, piece, move_opt)

        if first_move:
            inverted_value, _, time_exceeded = negamax(board, depth - 1, -beta, -alpha, start_time, time_limit, new_board_hash)
            value = -inverted_value
            first_move = False
        else:
            value, _, time_exceeded = negamax(board, depth - 1, -(alpha + 1), -alpha, start_time, time_limit, new_board_hash)
            value = -value
            if not time_exceeded and value > alpha:
                inverted_value, _, time_exceeded = negamax(board, depth - 1, -beta, -value, start_time, time_limit, new_board_hash)
                value = -inverted_value

        undo_move(board, info)
        undo_repetition_count(new_board_hash)

        if value > best_value:
            best_value = value
            best_move = (piece, move_opt)

        alpha = max(alpha, best_value)
        if alpha >= beta:
            break

        if time_exceeded:
            break

    memo[board_hash] = (best_value, best_move, depth)
    return best_value, best_move, time_exceeded


def agent(board: Board, player: Player, var: list[int]) -> Move:
    """
    This is an example of your designed Agent

    Parameters
    ----------
    board: the current chess board
    player: your assigned player role (white or black)
    var:  [ply, THINKING_TIME_BUDGET] a list cotaining the ply ID and the thinking_time_budget (secs)

    Returns
    -------
    piece: your selected chess piece
    move_opt: your selected move of your selected chess piece
    
    Hints:
    -----
    - List of players on the current board game: list(board.players) - default list: [Player (white), Player (black)]
    - board.players[0].name = "white" and board.players[1].name = "black"
    - Name of the player assigned to the Agent (either "white" or "black"): player.name
    - list of pieces of the current player: list(board.get_player_pieces(player))
    - List of pieces and corresponding moves for each pieces of the player: piece, move_opt = list_legal_moves_for(board, player)
    - From var: ply ID = var[0], timeout = var[1]
    - Use the timeout variable together with time.perf_counter()
    to ensure the agent returns its best move before the time limit expires.
    """
    start_time = time.perf_counter()
    time_limit = var[1] - 0.1  # Leave a small buffer

    global memo
    memo = {}
    take_notes(f"Ply: {var[0]}\ntime limit: {var[1]}\nmemo size: {len(memo)}\n")

    starting_depth = 1

    # Iterative deepening: progressively increase search depth while time remains.
    best_move = None
    best_value = float('-inf')
    depth = starting_depth
    board_hash = compute_hash(board, zobrist_table, zobrist_black_to_move)
    update_repetition_count(board_hash)

    while True:
        #new_board = clone_board(board)  # type: ignore[attr-defined]
        new_board = board
        value, move, time_exceeded = negamax(new_board, depth, float('-inf'), float('inf'), start_time, time_limit, board_hash)

        if time_exceeded:
            if value > best_value:
                best_move = move
                best_value = value
            break

        best_move = move
        best_value = value
        print_once(f"Completed depth {depth} (value = {best_value}, time = {time.perf_counter() - start_time:.6f}) ")
        depth += 1
        # break # ================================================== REMOVE AFTER TESTING =============================================

    print_once("")

    if best_move is None:
        raise Exception("No valid moves found by agent")
    
    print(f"Selected move with evaluation value: {best_value}")

    return best_move