from cProfile import Profile
from pstats import SortKey, Stats

def profile_agent(agent_function, board, player, var):
    profiler = Profile()
    profiler.enable()
    
    result = agent_function(board, player, var)
    
    profiler.disable()
    stats = (Stats(profiler)
        .strip_dirs()
        .sort_stats(SortKey.TIME) # or SortKey.CALLS
    )
    stats.print_stats()

    return result

from agent import agent
from samples import sample0
from test_fullgame import make_custom_board

if __name__ == "__main__":
    board, players = make_custom_board(sample0)
    player = players[0]
    var = [1, 30]  # [ply, thinking_time_budget]
    profile_agent(agent, board, player, var)
