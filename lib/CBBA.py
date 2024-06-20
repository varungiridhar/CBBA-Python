#!/usr/bin/env python3
import sys
import math
import copy
import matplotlib.pyplot as plt
import numpy as np
from Task import Task
from WorldInfo import WorldInfo


class CBBA(object):
    num_agents: int  # number of agents
    num_tasks: int  # number of tasks
    max_depth: int  # maximum bundle depth
    time_window_flag: bool  # True if time window exists
    duration_flag: bool  # Ture when all task duration > 0
    agent_types: list
    task_types: list
    space_limit_x: list  # [min, max] x coordinate [meter]
    space_limit_y: list  # [min, max] y coordinate [meter]
    space_limit_z: list  # [min, max] z coordinate [meter]
    time_interval_list: list  # time interval for all the agents and tasks
    agent_index_list: list  # 1D list
    bundle_list: list  # 2D list
    path_list: list  # 2D list
    times_list: list  # 2D list
    scores_list: list  # 2D list
    bid_list: list  # 2D list
    winners_list: list  # 2D list
    winner_bid_list: list  # 2D list
    graph: list  # 2D list represents the structure of graph
    AgentList: list  # 1D list, each entry is a dataclass Agent
    TaskList: list  # 1D list, each entry is a dataclass Task
    WorldInfo: WorldInfo  # a dataclass WorldInfo

    def __init__(self, config_data: dict):
        """
        Constructor
        Initialize CBBA Parameters

        config_data: dict, including all the configurations
            config_file_name = "config.json"
            json_file = open(config_file_name)
            config_data = json.load(json_file)
        """

        # List agent types 
        self.agent_types = config_data["AGENT_TYPES"]
        # List task types
        self.task_types = config_data["TASK_TYPES"]
        # time interval for all the agents and tasks
        self.time_interval_list = [min(int(config_data["TRACK_DEFAULT"]["START_TIME"]),
                                       int(config_data["RESCUE_DEFAULT"]["START_TIME"])),
                                   max(int(config_data["TRACK_DEFAULT"]["END_TIME"]),
                                       int(config_data["RESCUE_DEFAULT"]["END_TIME"]))]
        # Ture when all task duration > 0
        self.duration_flag = (min(int(config_data["TRACK_DEFAULT"]["DURATION"]),
                                  int(config_data["RESCUE_DEFAULT"]["DURATION"])) > 0)

        # Initialize Compatibility Matrix
        self.compatibility_mat = [[0] * len(self.task_types) for _ in range(len(self.agent_types))]

        # FOR USER TO DO: Set agent-task pairs (which types of agents can do which types of tasks)
        try:
            # quadrotor for track
            self.compatibility_mat[self.agent_types.index("quad")][self.task_types.index("track")] = 1
        except Exception as e:
            print(e)

        try:
            # car for rescue
            self.compatibility_mat[self.agent_types.index("car")][self.task_types.index("rescue")] = 1
        except Exception as e:
            print(e)

        self.fig_3d = plt.figure()
        self.ax_3d = plt.axes(projection='3d')
        plt.title('Agent Paths with Time Windows')
        self.ax_3d.set_xlabel("X")
        self.ax_3d.set_ylabel("Y")
        self.ax_3d.set_zlabel("Time")
        self.ax_3d.set_aspect('auto')

    def settings(self, AgentList: list, TaskList: list, WorldInfoInput: WorldInfo,
                 max_depth: int, time_window_flag: bool):
        """
        Initialize some lists given new AgentList, TaskList, and WorldInfoInput.
        """

        self.num_agents = len(AgentList)
        self.num_tasks = len(TaskList)
        self.max_depth = max_depth
        self.time_window_flag = time_window_flag

        self.AgentList = AgentList
        self.TaskList = TaskList

        # world information
        self.WorldInfo = WorldInfoInput
        self.space_limit_x = self.WorldInfo.limit_x
        self.space_limit_y = self.WorldInfo.limit_y
        self.space_limit_z = self.WorldInfo.limit_z

        # Fully connected graph
        # 2D list
        self.graph = np.logical_not(np.identity(self.num_agents)).tolist()

        # initialize these properties
        self.bundle_list = [[-1] * self.max_depth for _ in range(self.num_agents)]
        self.path_list = [[-1] * self.max_depth for _ in range(self.num_agents)]
        self.times_list = [[-1] * self.max_depth for _ in range(self.num_agents)]
        self.scores_list = [[-1] * self.max_depth for _ in range(self.num_agents)]

        # fixed the initialization, from 0 vector to -1 vector
        self.bid_list = [[-1] * self.num_tasks for _ in range(self.num_agents)]
        self.winners_list = [[-1] * self.num_tasks for _ in range(self.num_agents)]
        self.winner_bid_list = [[-1] * self.num_tasks for _ in range(self.num_agents)]

        self.agent_index_list = []
        for n in range(self.num_agents):
            self.agent_index_list.append(self.AgentList[n].agent_id)


    def solve(self, AgentList: list, TaskList: list, WorldInfoInput: WorldInfo,
              max_depth: int, time_window_flag: bool):
        """
        Main CBBA Function
        """

        # Initialize some lists given AgentList, TaskList, and WorldInfoInput.
        self.settings(AgentList, TaskList, WorldInfoInput, max_depth, time_window_flag)

        # Initialize working variables
        # Current iteration
        iter_idx = 1
        # Matrix of time of updates from the current winners
        time_mat = [[0] * self.num_agents for _ in range(self.num_agents)]
        iter_prev = 0
        done_flag = False

        # Main CBBA loop (runs until convergence)
        while not done_flag:

            # 1. Communicate
            # Perform consensus on winning agents and bid values (synchronous)
            time_mat = self.communicate(time_mat, iter_idx)

            # 2. Run CBBA bundle building/updating
            # Run CBBA on each agent (decentralized but synchronous)
            for idx_agent in range(self.num_agents):
                new_bid_flag = self.bundle(idx_agent)

                # Update last time things changed
                # needed for convergence but will be removed in the final implementation
                if new_bid_flag:
                    iter_prev = iter_idx

            # 3. Convergence Check
            # Determine if the assignment is over (implemented for now, but later this loop will just run forever)
            if (iter_idx - iter_prev) > self.num_agents:
                done_flag = True
            elif (iter_idx - iter_prev) > (2*self.num_agents):
                print("Algorithm did not converge due to communication trouble")
                done_flag = True
            else:
                # Maintain loop
                iter_idx += 1

        # Map path and bundle values to actual task indices
        for n in range(self.num_agents):
            for m in range(self.max_depth):
                if self.bundle_list[n][m] == -1:
                    break
                else:
                    self.bundle_list[n][m] = self.TaskList[self.bundle_list[n][m]].task_id

                if self.path_list[n][m] == -1:
                    break
                else:
                    self.path_list[n][m] = self.TaskList[self.path_list[n][m]].task_id

        # Compute the total score of the CBBA assignment
        score_total = 0
        for n in range(self.num_agents):
            for m in range(self.max_depth):
                if self.scores_list[n][m] > -1:
                    score_total += self.scores_list[n][m]
                else:
                    break

        # output the result path for each agent, delete all -1
        self.path_list = [list(filter(lambda a: a != -1, self.path_list[i]))
                          for i in range(len(self.path_list))]

        # delete redundant elements
        self.bundle_list = [list(filter(lambda a: a != -1, self.bundle_list[i]))
                            for i in range(len(self.bundle_list))]

        self.times_list = [list(filter(lambda a: a != -1, self.times_list[i]))
                           for i in range(len(self.times_list))]

        self.scores_list = [list(filter(lambda a: a != -1, self.scores_list[i]))
                            for i in range(len(self.scores_list))]

        return self.path_list, self.times_list

    def bundle(self, idx_agent: int):
        """
        Main CBBA bundle building/updating (runs on each individual agent)
        """

        # Update bundles after messaging to drop tasks that are outbid
        self.bundle_remove(idx_agent)
        # Bid on new tasks and add them to the bundle
        new_bid_flag = self.bundle_add(idx_agent)

        return new_bid_flag

    def bundle_remove(self, idx_agent: int):
        """
        Update bundles after communication
        For outbid agents, releases tasks from bundles
        """

        out_bid_for_task = False
        for idx in range(self.max_depth):
            # If bundle(j) < 0, it means that all tasks up to task j are
            # still valid and in paths, the rest (j to MAX_DEPTH) are released
            if self.bundle_list[idx_agent][idx] < 0:
                break
            else:
                # Test if agent has been outbid for a task.  If it has, release it and all subsequent tasks in its path.
                if self.winners_list[idx_agent][self.bundle_list[idx_agent][idx]] != self.agent_index_list[idx_agent]:
                    out_bid_for_task = True

                if out_bid_for_task:
                    # The agent has lost a previous task, release this one too
                    if self.winners_list[idx_agent][self.bundle_list[idx_agent][idx]] == \
                            self.agent_index_list[idx_agent]:
                        # Remove from winner list if in there
                        self.winners_list[idx_agent][self.bundle_list[idx_agent][idx]] = -1
                        self.winner_bid_list[idx_agent][self.bundle_list[idx_agent][idx]] = -1

                    # Clear from path and times vectors and remove from bundle
                    path_current = copy.deepcopy(self.path_list[idx_agent])
                    idx_remove = path_current.index(self.bundle_list[idx_agent][idx])

                    # remove item from list at location specified by idx_remove, then append -1 at the end.
                    del self.path_list[idx_agent][idx_remove]
                    self.path_list[idx_agent].append(-1)
                    del self.times_list[idx_agent][idx_remove]
                    self.times_list[idx_agent].append(-1)
                    del self.scores_list[idx_agent][idx_remove]
                    self.scores_list[idx_agent].append(-1)

                    self.bundle_list[idx_agent][idx] = -1

    def bundle_add(self, idx_agent: int):
        """
        Create bundles for each agent
        """

        epsilon = 1e-5
        new_bid_flag = False

        # Check if bundle is full, the bundle is full when bundle_full_flag is True
        index_array = np.where(np.array(self.bundle_list[idx_agent]) == -1)[0]
        if len(index_array) > 0:
            bundle_full_flag = False
        else:
            bundle_full_flag = True
        
        # Initialize feasibility matrix (to keep track of which j locations can be pruned)
        # feasibility = np.ones((self.num_tasks, self.max_depth+1))
        feasibility = [[1] * (self.max_depth+1) for _ in range(self.num_tasks)]

        while not bundle_full_flag:
            # Update task values based on current assignment
            [best_indices, task_times, feasibility] = self.compute_bid(idx_agent, feasibility)

            # Determine which assignments are available. array_logical_1, array_logical_2,
            # array_logical_13 are all numpy 1D bool array
            array_logical_1 = ((np.array(self.bid_list[idx_agent]) - np.array(self.winner_bid_list[idx_agent]))
                               > epsilon)
            # find the equal items
            array_logical_2 = (abs(np.array(self.bid_list[idx_agent]) - np.array(self.winner_bid_list[idx_agent]))
                               <= epsilon)
            # Tie-break based on agent index
            array_logical_3 = (self.agent_index_list[idx_agent] < np.array(self.winners_list[idx_agent]))

            array_logical_result = np.logical_or(array_logical_1, np.logical_and(array_logical_2, array_logical_3))

            # Select the assignment that will improve the score the most and place bid
            array_max = np.array(self.bid_list[idx_agent]) * array_logical_result
            best_task = array_max.argmax()
            value_max = max(array_max)

            if value_max > 0:
                # Set new bid flag
                new_bid_flag = True

                # Check for tie, return a 1D numpy array
                all_values = np.where(array_max == value_max)[0]
                if len(all_values) == 1:
                    best_task = all_values[0]
                else:
                    # Tie-break by which task starts first
                    earliest = sys.float_info.max
                    for i in range(len(all_values)):
                        if self.TaskList[all_values[i]].start_time < earliest:
                            earliest = self.TaskList[all_values[i]].start_time
                            best_task = all_values[i]
                
                self.winners_list[idx_agent][best_task] = self.AgentList[idx_agent].agent_id
                self.winner_bid_list[idx_agent][best_task] = self.bid_list[idx_agent][best_task]

                # Insert value into list at location specified by index, and delete the last one of original list.
                self.path_list[idx_agent].insert(best_indices[best_task], best_task)
                del self.path_list[idx_agent][-1]
                self.times_list[idx_agent].insert(best_indices[best_task], task_times[best_task])
                del self.times_list[idx_agent][-1]
                self.scores_list[idx_agent].insert(best_indices[best_task], self.bid_list[idx_agent][best_task])
                del self.scores_list[idx_agent][-1]

                length = len(np.where(np.array(self.bundle_list[idx_agent]) > -1)[0])
                self.bundle_list[idx_agent][length] = best_task

                # Update feasibility
                # This inserts the same feasibility boolean into the feasibility matrix
                for i in range(self.num_tasks):
                    # Insert value into list at location specified by index, and delete the last one of original list.
                    feasibility[i].insert(best_indices[best_task], feasibility[i][best_indices[best_task]])
                    del feasibility[i][-1]
            else:
                break

            # Check if bundle is full
            index_array = np.where(np.array(self.bundle_list[idx_agent]) == -1)[0]
            if len(index_array) > 0:
                bundle_full_flag = False
            else:
                bundle_full_flag = True

        return new_bid_flag

    def communicate(self, time_mat: list, iter_idx: int):
        """
        Runs consensus between neighbors. Checks for conflicts and resolves among agents.
        This is a message passing scheme described in Table 1 of: "Consensus-Based Decentralized Auctions for
        Robust Task Allocation", H.-L. Choi, L. Brunet, and J. P. How, IEEE Transactions on Robotics,
        Vol. 25, (4): 912 - 926, August 2009

        Note: Table 1 is the action rule for agent i based on communication with agent k regarding task j.
        The big for-loop with tons of if-else is the exact implementation of Table 1, for the sake of readability.
        """

        # time_mat is the matrix of time of updates from the current winners
        # iter_idx is the current iteration

        time_mat_new = copy.deepcopy(time_mat)

        # Copy data
        old_z = copy.deepcopy(self.winners_list)
        old_y = copy.deepcopy(self.winner_bid_list)
        z = copy.deepcopy(old_z)
        y = copy.deepcopy(old_y)

        epsilon = 10e-6

        # Start communication between agents
        # sender   = k
        # receiver = i
        # task     = j

        for k in range(self.num_agents):
            for i in range(self.num_agents):
                if self.graph[k][i] == 1:
                    for j in range(self.num_tasks):
                        # Implement table for each task

                        # Entries 1 to 4: Sender thinks he has the task
                        if old_z[k][j] == k:
                            
                            # Entry 1: Update or Leave
                            if z[i][j] == i:
                                if (old_y[k][j] - y[i][j]) > epsilon:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]
                                elif abs(old_y[k][j] - y[i][j]) <= epsilon:  # Equal scores
                                    if z[i][j] > old_z[k][j]:  # Tie-break based on smaller index
                                        z[i][j] = old_z[k][j]
                                        y[i][j] = old_y[k][j]

                            # Entry 2: Update
                            elif z[i][j] == k:
                                z[i][j] = old_z[k][j]
                                y[i][j] = old_y[k][j]
                    
                            # Entry 3: Update or Leave
                            elif z[i][j] > -1:
                                if time_mat[k][z[i][j]] > time_mat_new[i][z[i][j]]:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]
                                elif (old_y[k][j] - y[i][j]) > epsilon:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]
                                elif abs(old_y[k][j] - y[i][j]) <= epsilon:  # Equal scores
                                    if z[i][j] > old_z[k][j]:  # Tie-break based on smaller index
                                        z[i][j] = old_z[k][j]
                                        y[i][j] = old_y[k][j]

                            # Entry 4: Update
                            elif z[i][j] == -1:
                                z[i][j] = old_z[k][j]
                                y[i][j] = old_y[k][j]

                            else:
                                print(z[i][j])
                                raise Exception("Unknown winner value: please revise!")

                        # Entries 5 to 8: Sender thinks receiver has the task
                        elif old_z[k][j] == i:

                            # Entry 5: Leave
                            if z[i][j] == i:
                                # Do nothing
                                pass
                                
                            # Entry 6: Reset
                            elif z[i][j] == k:
                                z[i][j] = -1
                                y[i][j] = -1

                            # Entry 7: Reset or Leave
                            elif z[i][j] > -1:
                                if time_mat[k][z[i][j]] > time_mat_new[i][z[i][j]]:  # Reset
                                    z[i][j] = -1
                                    y[i][j] = -1
                                
                            # Entry 8: Leave
                            elif z[i][j] == -1:
                                # Do nothing
                                pass

                            else:
                                print(z[i][j])
                                raise Exception("Unknown winner value: please revise!")

                        # Entries 9 to 13: Sender thinks someone else has the task
                        elif old_z[k][j] > -1:
                            
                            # Entry 9: Update or Leave
                            if z[i][j] == i:
                                if time_mat[k][old_z[k][j]] > time_mat_new[i][old_z[k][j]]:
                                    if (old_y[k][j] - y[i][j]) > epsilon:
                                        z[i][j] = old_z[k][j]  # Update
                                        y[i][j] = old_y[k][j]
                                    elif abs(old_y[k][j] - y[i][j]) <= epsilon:  # Equal scores
                                        if z[i][j] > old_z[k][j]:  # Tie-break based on smaller index
                                            z[i][j] = old_z[k][j]
                                            y[i][j] = old_y[k][j]

                            # Entry 10: Update or Reset
                            elif z[i][j] == k:
                                if time_mat[k][old_z[k][j]] > time_mat_new[i][old_z[k][j]]:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]
                                else:  # Reset
                                    z[i][j] = -1
                                    y[i][j] = -1

                            # Entry 11: Update or Leave
                            elif z[i][j] == old_z[k][j]:
                                if time_mat[k][old_z[k][j]] > time_mat_new[i][old_z[k][j]]:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]

                            # Entry 12: Update, Reset or Leave
                            elif z[i][j] > -1:
                                if time_mat[k][z[i][j]] > time_mat_new[i][z[i][j]]:
                                    if time_mat[k][old_z[k][j]] >= time_mat_new[i][old_z[k][j]]:  # Update
                                        z[i][j] = old_z[k][j]
                                        y[i][j] = old_y[k][j]
                                    elif time_mat[k][old_z[k][j]] < time_mat_new[i][old_z[k][j]]:  # Reset
                                        z[i][j] = -1
                                        y[i][j] = -1
                                    else:
                                        raise Exception("Unknown condition for Entry 12: please revise!")
                                else:
                                    if time_mat[k][old_z[k][j]] > time_mat_new[i][old_z[k][j]]:
                                        if (old_y[k][j] - y[i][j]) > epsilon:  # Update
                                            z[i][j] = old_z[k][j]
                                            y[i][j] = old_y[k][j]
                                        elif abs(old_y[k][j] - y[i][j]) <= epsilon:  # Equal scores
                                            if z[i][j] > old_z[k][j]:  # Tie-break based on smaller index
                                                z[i][j] = old_z[k][j]
                                                y[i][j] = old_y[k][j]

                            # Entry 13: Update or Leave
                            elif z[i][j] == -1:
                                if time_mat[k][old_z[k][j]] > time_mat_new[i][old_z[k][j]]:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]

                            else:
                                raise Exception("Unknown winner value: please revise!")

                        # Entries 14 to 17: Sender thinks no one has the task
                        elif old_z[k][j] == -1:

                            # Entry 14: Leave
                            if z[i][j] == i:
                                # Do nothing
                                pass

                            # Entry 15: Update
                            elif z[i][j] == k:
                                z[i][j] = old_z[k][j]
                                y[i][j] = old_y[k][j]

                            # Entry 16: Update or Leave
                            elif z[i][j] > -1:
                                if time_mat[k][z[i][j]] > time_mat_new[i][z[i][j]]:  # Update
                                    z[i][j] = old_z[k][j]
                                    y[i][j] = old_y[k][j]

                            # Entry 17: Leave
                            elif z[i][j] == -1:
                                # Do nothing
                                pass
                            else:
                                raise Exception("Unknown winner value: please revise!")

                            # End of table
                        else:
                            raise Exception("Unknown winner value: please revise!")

                    # Update timestamps for all agents based on latest comm
                    for n in range(self.num_agents):
                        if (n != i) and (time_mat_new[i][n] < time_mat[k][n]):
                            time_mat_new[i][n] = time_mat[k][n]
                    time_mat_new[i][k] = iter_idx

        # Copy data
        self.winners_list = copy.deepcopy(z)
        self.winner_bid_list = copy.deepcopy(y)
        return time_mat_new

    def compute_bid(self, idx_agent: int, feasibility: list):
        """
        Computes bids for each task. Returns bids, best index for task in
        the path, and times for the new path
        """

        # If the path is full then we cannot add any tasks to it
        empty_task_index_list = np.where(np.array(self.path_list[idx_agent]) == -1)[0]
        if len(empty_task_index_list) == 0:
            best_indices = []
            task_times = []
            feasibility = []
            return best_indices, task_times, feasibility

        # Reset bids, best positions in path, and best times
        self.bid_list[idx_agent] = [-1] * self.num_tasks
        best_indices = [-1] * self.num_tasks
        task_times = [-2] * self.num_tasks

        # For each task
        for idx_task in range(self.num_tasks):
            # Check for compatibility between agent and task
            # for floating precision
            if self.compatibility_mat[self.AgentList[idx_agent].agent_type][self.TaskList[idx_task].task_type] > 0.5:
                
                # Check to make sure the path doesn't already contain task m
                index_array = np.where(np.array(self.path_list[idx_agent][0:empty_task_index_list[0]]) == idx_task)[0]
                if len(index_array) < 0.5:
                    # this task not in my bundle yet
                    # Find the best score attainable by inserting the score into the current path
                    best_bid = 0
                    best_index = -1
                    best_time = -2

                    # Try inserting task m in location j among other tasks and see if it generates a better new_path.
                    for j in range(empty_task_index_list[0]+1):
                        if feasibility[idx_task][j] == 1:
                            # Check new path feasibility, true to skip this iteration, false to be feasible
                            skip_flag = False

                            if j == 0:
                                # insert at the beginning
                                task_prev = []
                                time_prev = []
                            else:
                                Task_temp = self.TaskList[self.path_list[idx_agent][j-1]]
                                task_prev = Task(**Task_temp.__dict__)
                                time_prev = self.times_list[idx_agent][j-1]
                            
                            if j == (empty_task_index_list[0]):
                                task_next = []
                                time_next = []
                            else:
                                Task_temp = self.TaskList[self.path_list[idx_agent][j]]
                                task_next = Task(**Task_temp.__dict__)
                                time_next = self.times_list[idx_agent][j]

                            # Compute min and max start times and score
                            Task_temp = self.TaskList[idx_task]
                            [score, min_start, max_start] = self.scoring_compute_score(
                                idx_agent, Task(**Task_temp.__dict__), task_prev, time_prev, task_next, time_next)

                            if self.time_window_flag:
                                # if tasks have time window
                                if min_start > max_start:
                                    # Infeasible path
                                    skip_flag = True
                                    feasibility[idx_task][j] = 0

                                if not skip_flag:
                                    # Save the best score and task position
                                    if score > best_bid:
                                        best_bid = score
                                        best_index = j
                                        # Select min start time as optimal
                                        best_time = min_start
                            else:
                                # no time window for tasks
                                # Save the best score and task position
                                if score > best_bid:
                                    best_bid = score
                                    best_index = j
                                    # Select min start time as optimal
                                    best_time = 0.0

                    # save best bid information
                    if best_bid > 0:
                        self.bid_list[idx_agent][idx_task] = best_bid
                        best_indices[idx_task] = best_index
                        task_times[idx_task] = best_time

            # this task is incompatible with my type
        # end loop through tasks
        return best_indices, task_times, feasibility

    def scoring_compute_score(self, idx_agent: int, task_current: Task, task_prev: Task,
                              time_prev, task_next: Task, time_next):
        """
        Compute marginal score of doing a task and returns the expected start time for the task.
        """

        if (self.AgentList[idx_agent].agent_type == self.agent_types.index("quad")) or \
                (self.AgentList[idx_agent].agent_type == self.agent_types.index("car")):
            
            if not task_prev:
                # First task in path
                # Compute start time of task
                dt = math.sqrt((self.AgentList[idx_agent].x-task_current.x)**2 +
                               (self.AgentList[idx_agent].y-task_current.y)**2 +
                               (self.AgentList[idx_agent].z-task_current.z)**2) / self.AgentList[idx_agent].nom_velocity
                min_start = max(task_current.start_time, self.AgentList[idx_agent].availability + dt)
            else:
                # Not first task in path
                dt = math.sqrt((task_prev.x-task_current.x)**2 + (task_prev.y-task_current.y)**2 +
                               (task_prev.z-task_current.z)**2) / self.AgentList[idx_agent].nom_velocity
                # i have to have time to do task at j-1 and go to task m
                min_start = max(task_current.start_time, time_prev + task_prev.duration + dt)

            if not task_next:
                # Last task in path
                dt = 0.0
                max_start = task_current.end_time
            else:
                # Not last task, check if we can still make promised task
                dt = math.sqrt((task_next.x-task_current.x)**2 + (task_next.y-task_current.y)**2 +
                               (task_next.z-task_current.z)**2) / self.AgentList[idx_agent].nom_velocity
                # i have to have time to do task m and fly to task at j+1
                max_start = min(task_current.end_time, time_next - task_current.duration - dt)

            # Compute score
            if self.time_window_flag:
                # if tasks have time window
                reward = task_current.task_value * \
                         math.exp((-task_current.discount) * (min_start-task_current.start_time))
            else:
                # no time window for tasks
                dt_current = math.sqrt((self.AgentList[idx_agent].x-task_current.x)**2 +
                                       (self.AgentList[idx_agent].y-task_current.y)**2 +
                                       (self.AgentList[idx_agent].z-task_current.z)**2) / \
                             self.AgentList[idx_agent].nom_velocity

                reward = task_current.task_value * math.exp((-task_current.discount) * dt_current)

            # # Subtract fuel cost. Implement constant fuel to ensure DMG (diminishing marginal gain).
            # # This is a fake score since it double-counts fuel. Should not be used when comparing to optimal score.
            # # Need to compute real score of CBBA paths once CBBA algorithm has finished running.
            # penalty = self.AgentList[idx_agent].fuel * math.sqrt(
            #     (self.AgentList[idx_agent].x-task_current.x)**2 + (self.AgentList[idx_agent].y-task_current.y)**2 +
            #     (self.AgentList[idx_agent].z-task_current.z)**2)
            #
            # score = reward - penalty

            score = reward
        else:
            # FOR USER TO DO:  Define score function for specialized agents, for example:
            # elseif(agent.type == CBBA_Params.AGENT_TYPES.NEW_AGENT), ...  
            # Need to define score, minStart and maxStart
            raise Exception("Unknown agent type!")

        return score, min_start, max_start

    def plot_assignment(self):
        """
        Plots CBBA outputs when there is time window for tasks.
        """
        # clear this axes
        self.ax_3d.clear()

        # offset to plot text in 3D space
        offset = (self.WorldInfo.limit_x[1]-self.WorldInfo.limit_x[0]) / 50

        # plot tasks
        for m in range(self.num_tasks):
            # track task is red
            if self.TaskList[m].task_type == 0:
                color_str = 'red'
            # rescue task is blue
            else:
                color_str = 'blue'

            self.ax_3d.scatter([self.TaskList[m].x]*2, [self.TaskList[m].y]*2,
                          [self.TaskList[m].start_time, self.TaskList[m].end_time], marker='x', color=color_str)
            self.ax_3d.plot3D([self.TaskList[m].x]*2, [self.TaskList[m].y]*2,
                         [self.TaskList[m].start_time, self.TaskList[m].end_time],
                         linestyle=':', color=color_str, linewidth=3)
            self.ax_3d.text(self.TaskList[m].x+offset, self.TaskList[m].y+offset, self.TaskList[m].start_time, "T"+str(m))

        # plot agents
        for n in range(self.num_agents):
            # quad agent is red
            if self.AgentList[n].agent_type == 0:
                color_str = 'red'
            # car agent is blue
            else:
                color_str = 'blue'
            self.ax_3d.scatter(self.AgentList[n].x, self.AgentList[n].y, 0, marker='o', color=color_str)
            self.ax_3d.text(self.AgentList[n].x+offset, self.AgentList[n].y+offset, 0.1, "A"+str(n))

            # if the path is not empty
            if self.path_list[n]:
                Task_prev = self.lookup_task(self.path_list[n][0])
                self.ax_3d.plot3D([self.AgentList[n].x, Task_prev.x], [self.AgentList[n].y, Task_prev.y],
                             [0, self.times_list[n][0]], linewidth=2, color=color_str)
                self.ax_3d.plot3D([Task_prev.x, Task_prev.x], [Task_prev.y, Task_prev.y],
                             [self.times_list[n][0], self.times_list[n][0]+Task_prev.duration],
                             linewidth=2, color=color_str)

                for m in range(1, len(self.path_list[n])):
                    if self.path_list[n][m] > -1:
                        Task_next = self.lookup_task(self.path_list[n][m])
                        self.ax_3d.plot3D([Task_prev.x, Task_next.x], [Task_prev.y, Task_next.y],
                                     [self.times_list[n][m-1]+Task_prev.duration, self.times_list[n][m]],
                                     linewidth=2, color=color_str)
                        self.ax_3d.plot3D([Task_next.x, Task_next.x], [Task_next.y, Task_next.y],
                                     [self.times_list[n][m], self.times_list[n][m]+Task_next.duration],
                                     linewidth=2, color=color_str)
                        Task_prev = Task(**Task_next.__dict__)
        # set legends
        colors = ["red", "blue", "red", "blue"]
        marker_list = ["o", "o", "x", "x"]
        labels = ["Agent type 1", "Agent type 2", "Task type 1", "Task type 2"]
        def f(marker_type, color_type): return plt.plot([], [], marker=marker_type, color=color_type, ls="none")[0]
        handles = [f(marker_list[i], colors[i]) for i in range(len(labels))]
        plt.legend(handles, labels, bbox_to_anchor=(1, 1), loc='upper left', framealpha=1)
        self.set_axes_equal_xy(self.ax_3d, flag_3d=True)

        if self.duration_flag:
            # plot agent schedules
            fig_schedule = plt.figure(2)
            fig_schedule.suptitle("Schedules for Agents")
            for idx_agent in range(self.num_agents):
                ax = plt.subplot(self.num_agents, 1, idx_agent+1)
                ax.set_title("Agent "+str(idx_agent))
                if idx_agent == (self.num_agents - 1):
                    ax.set_xlabel("Time [sec]")
                ax.set_xlim(self.time_interval_list)
                ax.set_ylim([0.95, 1.05])

                # quad agent is red
                if self.AgentList[idx_agent].agent_type == 0:
                    color_str = 'red'
                # car agent is blue
                else:
                    color_str = 'blue'

                if self.path_list[idx_agent]:
                    for idx_path in range(len(self.path_list[idx_agent])):
                        if self.path_list[idx_agent][idx_path] > -1:
                            task_current = self.lookup_task(self.path_list[idx_agent][idx_path])
                            ax.plot([self.times_list[idx_agent][idx_path],
                                     self.times_list[idx_agent][idx_path]+task_current.duration], [1, 1],
                                    linestyle='-', linewidth=10, color=color_str, alpha=0.5)
                            ax.plot([task_current.start_time, task_current.end_time], [1, 1], linestyle='-.',
                                    linewidth=2, color=color_str)

            # set legends
            colors = ["red", "red"]
            line_styles = ["-", "-."]
            line_width_list = [10, 2]
            labels = ["Assignment Time", "Task Time"]
            def f(line_style, color_type, line_width): return plt.plot([], [], linestyle=line_style, color=color_type,
                                                                       linewidth=line_width)[0]
            handles = [f(line_styles[i], colors[i], line_width_list[i]) for i in range(len(labels))]
            fig_schedule.legend(handles, labels, bbox_to_anchor=(1, 1), loc='upper left', framealpha=1)


    def plot_assignment_without_timewindow(self):
        """
        Plots CBBA outputs when there is no time window for tasks.
        """

        # 3D plot
        fig = plt.figure()
        ax = fig.add_subplot(111)
        # offset to plot text in 3D space
        offset = (self.WorldInfo.limit_x[1]-self.WorldInfo.limit_x[0]) / 100

        # plot tasks
        for m in range(self.num_tasks):
            # track task is red
            if self.TaskList[m].task_type == 0:
                color_str = 'red'
            # rescue task is blue
            else:
                color_str = 'blue'
            ax.scatter(self.TaskList[m].x, self.TaskList[m].y, marker='x', color=color_str)
            ax.text(self.TaskList[m].x+offset, self.TaskList[m].y+offset, "T"+str(m))

        # plot agents
        for n in range(self.num_agents):
            # quad agent is red
            if self.AgentList[n].agent_type == 0:
                color_str = 'red'
            # car agent is blue
            else:
                color_str = 'blue'
            ax.scatter(self.AgentList[n].x, self.AgentList[n].y, marker='o', color=color_str)
            ax.text(self.AgentList[n].x+offset, self.AgentList[n].y+offset, "A"+str(n))

            # if the path is not empty
            if self.path_list[n]:
                Task_prev = self.lookup_task(self.path_list[n][0])
                ax.plot([self.AgentList[n].x, Task_prev.x], [self.AgentList[n].y, Task_prev.y],
                        linewidth=2, color=color_str)
                for m in range(1, len(self.path_list[n])):
                    if self.path_list[n][m] > -1:
                        Task_next = self.lookup_task(self.path_list[n][m])
                        ax.plot([Task_prev.x, Task_next.x], [Task_prev.y, Task_next.y], linewidth=2, color=color_str)
                        Task_prev = Task(**Task_next.__dict__)
        
        plt.title('Agent Paths without Time Windows')
        ax.set_xlabel("X")
        ax.set_ylabel("Y")

        # set legends
        colors = ["red", "blue", "red", "blue"]
        marker_list = ["o", "o", "x", "x"]
        labels = ["Agent type 1", "Agent type 2", "Task type 1", "Task type 2"]
        def f(marker_type, color_type): return plt.plot([], [], marker=marker_type, color=color_type, ls="none")[0]
        handles = [f(marker_list[i], colors[i]) for i in range(len(labels))]
        plt.legend(handles, labels, bbox_to_anchor=(1, 1), loc='upper left', framealpha=1)

        self.set_axes_equal_xy(ax, flag_3d=False)
        plt.show(block=False)

    def set_axes_equal_xy(self, ax, flag_3d: bool):
        """
        Make only x and y axes of 3D plot have equal scale. This is one possible solution to Matplotlib's
        ax.set_aspect('equal') and ax.axis('equal') not working for 3D.
        Reference: https://stackoverflow.com/questions/13685386/matplotlib-equal-unit-length-with-equal-aspect-ratio-z-axis-is-not-equal-to

        Input
        ax: a matplotlib axis, e.g., as output from plt.gca().
        flag_3d: boolean, True if it's 3D plot.
        """

        x_limits = self.space_limit_x
        y_limits = self.space_limit_y

        x_range = abs(x_limits[1] - x_limits[0])
        x_middle = np.mean(x_limits)
        y_range = abs(y_limits[1] - y_limits[0])
        y_middle = np.mean(y_limits)

        # The plot bounding box is a sphere in the sense of the infinity
        # norm, hence I call half the max range the plot radius.
        plot_radius = 0.5*max([x_range, y_range])

        if flag_3d:
            ax.set_xlim3d([x_middle - plot_radius, x_middle + plot_radius])
            ax.set_ylim3d([y_middle - plot_radius, y_middle + plot_radius])
            if abs(self.time_interval_list[1]) >= 1e-3:
                ax.set_zlim3d(self.time_interval_list)
        else:
            ax.set_xlim([x_middle - plot_radius, x_middle + plot_radius])
            ax.set_ylim([y_middle - plot_radius, y_middle + plot_radius])

    def lookup_task(self, task_id: int):
        """
        Look up a Task given the task ID.
        """

        TaskOutput = []
        for m in range(self.num_tasks):
            if self.TaskList[m].task_id == task_id:
                Task_temp = self.TaskList[m]
                TaskOutput.append(Task(**Task_temp.__dict__))

        if not TaskOutput:
            raise Exception("Task " + str(task_id) + " not found!")

        return TaskOutput[0]
