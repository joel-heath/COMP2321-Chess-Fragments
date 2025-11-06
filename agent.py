import time
from extension.board_utils import list_legal_moves_for, copy_piece_move, take_notes
from extension.board_rules import _update_repetition_count, only_2kings, cannot_move
from chessmaker.chess.base import Board, Player, Piece, MoveOption
from chessmaker.chess.pieces import King
from typing import Iterable

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


# == BOARD STATE ==

def is_draw(board: Board) -> str | None:
    rep_count = _update_repetition_count(board)
    if rep_count >= 5:
        return "Draw - fivefold repetition"
    return only_2kings(board)


def is_loss(board) -> str | None:
    return cannot_move(board)


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


def sortKey(board: Board, piece: Piece, move_opt: MoveOption) -> int:
    score = 0
    
    # check if is check:
    #if move_is_check(board, piece, move_opt):
    #    score += 1000

    # Most Valuable Victim - Least Valuable Aggressor

    if move_opt.captures:
        captured_position = next(iter(move_opt.captures))
        captured_square = board.__getitem__(captured_position) # type: ignore[attr-defined]
        captured_piece = captured_square.piece                 # type: ignore[attr-defined]

        captured_value = piece_value(captured_piece)
        attacker_value = piece_value(piece)
        score += captured_value * 10 - attacker_value
    
    return score


# == NEGAMAX WITH ALPHA-BETA PRUNING ==

def negamax(board: Board, depth: int, alpha: float, beta: float, start_time: float, time_limit: float) -> tuple[float, tuple[Piece, MoveOption] | None, bool]:
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
    if depth <= 0:
        return evaluate_board(board), None, False
    if is_draw(board):
        return 0, None, False
    if is_loss(board):
        return -100_000 - depth, None, False

    player = board.current_player # type: ignore[attr-defined] (pylance is DUMBFOUNDINGLY stupid sometimes (all the time))
    best_value = float('-inf')
    best_move = None
    time_exceeded = False
    first_move = True

    moves: list[tuple[Piece, MoveOption]] = list_legal_moves_for(board, player)
    moves.sort(key = lambda move: sortKey(board, move[0], move[1]), reverse=True)
    for piece, move_opt in moves:
        new_piece: Piece; new_move_opt: MoveOption; new_board: Board
        new_board = clone_board(board)                                           # type: ignore[attr-defined]
        _, new_piece, new_move_opt = copy_piece_move(new_board, piece, move_opt) # type: ignore[attr-defined]
        new_piece.move(new_move_opt)                                             # type: ignore[attr-defined]

        if first_move:
            inverted_value, _, time_exceeded = negamax(new_board, depth - 1, -beta, -alpha, start_time, time_limit)
            value = -inverted_value
            first_move = False
        else:
            value, _, time_exceeded = negamax(new_board, depth - 1, -(alpha + 1), -alpha, start_time, time_limit)
            value = -value
            if not time_exceeded and value > alpha:
                inverted_value, _, time_exceeded = negamax(new_board, depth - 1, -beta, -value, start_time, time_limit)
                value = -inverted_value

        if time_exceeded:
            break

        if value > best_value:
            best_value = value
            best_move = (piece, move_opt)

        alpha = max(alpha, best_value)
        if alpha >= beta:
            break

    return best_value, best_move, time_exceeded


def agent(board: Board, player: Player, var: list[int]) -> tuple[Piece, MoveOption]:
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
    print(f"Ply: {var[0]}")

    starting_depth = 1

    start_time = time.perf_counter()
    time_limit = var[1] - 0.5  # Leave a small buffer

    # Iterative deepening: progressively increase search depth while time remains.
    best_move = None
    best_value = float('-inf')
    depth = starting_depth

    # Keep searching deeper until we run out of time. Use clones per search to avoid
    # polluting the original board state.
    while True:
        new_board = clone_board(board)  # type: ignore[attr-defined]
        value, move, time_exceeded = negamax(new_board, depth, float('-inf'), float('inf'), start_time, time_limit)

        if time_exceeded:
            if value > best_value:
                best_move = move
                best_value = value
            break

        best_move = move
        best_value = value
        print_once(f"Completed depth {depth} (value={best_value})")
        depth += 1

    print_once("")

    # Ensure there's a selected move before proceeding
    if best_move is not None:
        value = best_value
        piece, move_opt = best_move
    else:
        raise Exception("No valid moves found by agent")
    
    print(f"Selected move with evaluation value: {value}")

    return piece, move_opt