import time
from extension.board_utils import list_legal_moves_for, copy_piece_move, take_notes
from extension.board_rules import _update_repetition_count, only_2kings, cannot_move
from chessmaker.chess.base import Board, Player, Piece, MoveOption
from typing import Iterable

# == DEBUGGING ==
print_once_last_message : str = ""
print_once_count : int = 0

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


# == BOARD RULES ==

def is_draw(board: Board) -> str | None:
    rep_count = _update_repetition_count(board)
    if rep_count >= 5:
        return "Draw - fivefold repetition"
    return only_2kings(board)


def is_loss(board) -> str | None:
    return cannot_move(board)


# == EVALUATION ==

def piece_value(piece: Piece) -> int:
    """
    Returns the value of a piece based on its type.
    """
    piece_name : str = piece.name # type: ignore[attr-defined]

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


def evaluate_board(board : Board):
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
    current_player : Player = board.current_player  # type: ignore[attr-defined]
    pieces : Iterable[Piece] = board.get_pieces() # type: ignore[attr-defined]

    for piece in pieces:
        value = piece_value(piece)
        piece_player : Player = piece.player  # type: ignore[attr-defined]
        if piece_player == current_player:
            score += value
        else:
            score -= value
    return score


# == NEGAMAX WITH ALPHA-BETA PRUNING ==

def negamax(board : Board, depth : int, alpha : float, beta : float, start_time : float, time_limit : float) -> tuple[float, tuple[Piece, MoveOption] | None]:
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
    """
    
    if time.perf_counter() - start_time > time_limit:
        print_once("Time limit exceeded during search")
        return 0, None
    if depth <= 0:
        return evaluate_board(board), None
    if is_draw(board):
        return 0, None
    if is_loss(board):
        return -100_000 - depth, None

    player = board.current_player # type: ignore[attr-defined] (pylance is DUMBFOUNDINGLY stupid sometimes (all the time))
    best_value = float('-inf')
    best_move = None

    moves : list[tuple[Piece, MoveOption]] = list_legal_moves_for(board, player)
    for piece, move_opt in moves:
        new_piece : Piece; new_move_opt : MoveOption; new_board : Board
        new_board = board.clone()                                                # type: ignore[attr-defined]
        _, new_piece, new_move_opt = copy_piece_move(new_board, piece, move_opt) # type: ignore[attr-defined]
        new_piece.move(new_move_opt)                                             # type: ignore[attr-defined]

        value, _ = negamax(new_board, depth - 1, -beta, -alpha, start_time, time_limit)
        value = -value

        if value > best_value:
            best_value = value
            best_move = (piece, move_opt)

        alpha = max(alpha, best_value)
        if alpha >= beta:
            break  # Beta cut-off

    return best_value, best_move


def agent(board : Board, player : Player, var : list[int]) -> tuple[Piece, MoveOption]:
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

    depth = 4
    start_time = time.perf_counter()
    time_limit = var[1] - 1  # Leave a small buffer
    new_board = board.clone() # type: ignore[attr-defined]

    value, best_move = negamax(new_board, depth, float('-inf'), float('inf'), start_time, time_limit)
    print_once("") # Puts a newline if there were repeated messages

    if best_move is not None:
        piece, move_opt = best_move
    else:
        raise Exception("No valid moves found by agent")

    print(f"Selected move with evaluation value: {value}")

    return piece, move_opt