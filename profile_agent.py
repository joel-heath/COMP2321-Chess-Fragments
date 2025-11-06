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

import time
def time_agent(agent_function, board, player, var):
    start_time = time.perf_counter()
    agent_function(board, player, var)
    end_time = time.perf_counter()
    total_time = end_time - start_time
    print(f"{total_time:.6f} seconds")
    return total_time

from agent import agent
from samples import sample0
from test_fullgame import make_custom_board

if __name__ == "__main__":
    board, players = make_custom_board(sample0)
    player = players[0]
    var = [1, 30]  # [ply, thinking_time_budget]

    time_agent(agent, board, player, var)
    # profile_agent(agent, board, player, var)

# measured in seconds

# depth |       DFS | IDS
# ------|-----------|----
#     1 |  0.025014 | 
#     2 |  0.220387 |
#     3 |  1.242618 |
#     4 |  5.039525 |
#     5 | 13.115289 |
#     6 | 94.537617 |

