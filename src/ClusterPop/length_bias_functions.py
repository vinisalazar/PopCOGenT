import numpy as np
from collections import Counter
import itertools

def parse_alignment_file(alignment, min_block_size=1000, filtering_window=1000):

    # Initializes local variables
    filtered_blocks = []
    all_blocks, prefilter_total_len = get_concatenated_alignment(alignment)

    # Filter alignment to split into subblocks at any point where there are at least 2 gaps
    for prefilter_s1, prefilter_s2 in all_blocks:
        filtered_blocks += filter_block(prefilter_s1, prefilter_s2)
    filtered_blocks = [block for block in filtered_blocks if len(block[0]) > min_block_size]
    s1temp, s2temp = zip(*filtered_blocks)

    # Assumes that each alignment block adds another divergence
    Concat_S1 = '1'.join(s1temp)
    Concat_S2 = '0'.join(s2temp)
    alignment_size = len(Concat_S1)
    init_div_count = naive_div_count(Concat_S1, Concat_S2)
    init_div = init_div_count * 1.0 / alignment_size

    # Second filtering step by divergence 
    final_filtered = []
    for s1, s2 in filtered_blocks:
        final_filtered += filter_block_by_divergence(s1, s2, init_div, winlen=filtering_window)
    filtered_blocks = [block for block in final_filtered if len(block[0]) > min_block_size]
    s1temp, s2temp = zip(*filtered_blocks)

    # Assumes that each alignment block adds another divergence
    Concat_S1 = '1'.join(s1temp)
    Concat_S2 = '0'.join(s2temp)
    alignment_size = len(Concat_S1)
    init_div_count = naive_div_count(Concat_S1, Concat_S2)
    init_div = (init_div_count * 1.0) / alignment_size

    initial = id_var_window_counts(Concat_S1, Concat_S2)
    initial_cumulative = get_cumulative_window_spectrum(initial, alignment_size)

    return (initial_cumulative, init_div)


def get_cumulative_window_spectrum(idw, gs):
    '''
    Gets the X and Y coordinates of the identical window spectrum
    i.e., the fraction of the genome belonging to identical windows
    above a certain size
    '''

    obs_frac_counts = np.zeros(gs)
    norm = np.sum(idw)
    windows = Counter(idw)
    for wsize, count in windows.items():
        obs_frac_counts[wsize] = count * wsize * 1.0 / norm
    return 1.0 - np.cumsum(obs_frac_counts)


def get_concatenated_alignment(alignment):
    '''
    This creates a list of tuples that constitute a concatenated alignment.
    Every entry in the list is a tuple that corresponds to an alignment block.
    '''

    with open(alignment, 'r') as infile:
        '''
        Parser assumes a maf format where every alignment block begins with a
        statement of how many sequences are in that block, indicated by
        "mult=." Also assumes that the order of sequences in each block is
        the same.
        '''
        seqs = []
        total_len = 0
        for lines in infile:
            if 'mult=2' in lines:
                seq_line_1 = next(infile)
                block_1 = seq_line_1.split()[-1].strip()
                total_len += len(block_1)
                seq_line_2 = next(infile)
                block_2 = seq_line_2.split()[-1].replace('\n', '')
                seqs.append((block_1, block_2))
    return seqs, total_len


def id_var_window_counts(sequence_1, sequence_2):
    '''
    This method takes two aligned sequences (strings) and returns the
    lengths of all identical windows between those sequences.
    '''
    if sequence_1 == sequence_2:
        id_seqs = [len(sequence_1)]
    else:
        a1 = np.array(list(sequence_1))
        a2 = np.array(list(sequence_2))
        mutated_positions = np.where(a1 != a2)[0]
        id_seqs = -1 + np.ediff1d(mutated_positions,
                                  to_begin=mutated_positions[0] + 1,
                                  to_end=len(sequence_1) - mutated_positions[-1])
    return id_seqs


def naive_div_count(sequence_1, sequence_2):
    '''
    Given two aligned strings, returns the number of differences between them.
    '''
    if sequence_1 == sequence_2:
        return 0
    a1 = np.array(list(sequence_1))
    a2 = np.array(list(sequence_2))
    return len(np.where(a1 != a2)[0])


def filter_block(sequence_1, sequence_2):
    removal_positions = filter_string(sequence_1)
    removal_positions += filter_string(sequence_2)
    return [block for block in get_filtered_subblocks(sequence_1, sequence_2, removal_positions) if block[0] != '']


def filter_string(S):
    groups = itertools.groupby(S)
    result = [(label, sum(1 for _ in group)) for label, group in groups]
    begin = 0
    filter_intervals = []
    for base, count in result:
        end = begin + count
        if base == '-' and count >= 2:
            filter_intervals.append((end, begin))
        begin += count
    return(filter_intervals)


def filter_block_by_divergence(sequence_1, sequence_2, init_div, winlen=1000):
    '''
    Filters two sequences from an alignment block to remove regions
    that are significantly more diverged than expected
    '''

    if sequence_1 == sequence_2:
        return [(sequence_1, sequence_2)]
    else:
        removal_positions = []
        begin = 0
        for end in range(winlen, len(sequence_1), winlen):
            d = naive_div_count(sequence_1[begin:end], sequence_2[begin:end])
            if d / winlen >= 10 * init_div:
                removal_positions.append((end, begin))
            begin = end

        if begin < len(sequence_1):
            d = naive_div_count(sequence_1[begin:], sequence_2[begin:])
            if d / (len(sequence_1) - begin) >= 10 * init_div:
                removal_positions.append((len(sequence_1), begin))

        return [block for block in get_filtered_subblocks(sequence_1, sequence_2, removal_positions) if block[0] != '']


def get_filtered_subblocks(sequence_1, sequence_2, positions_to_remove):
    '''
    Helper method that splits a string into substrings when given a list of
    start and end positions to remove
    '''
    if positions_to_remove == []:
        return [(sequence_1, sequence_2)]
    else:
        final_blocks = []
        initial_start = 0
        if len(positions_to_remove) > 1:
            merged = merge_intervals(sorted(positions_to_remove, reverse=True))
        else:
            merged = positions_to_remove
        ends, starts = zip(*sorted(merged, key=lambda x: x[1]))
        for i, start_of_deleted_region in enumerate(starts):
            end_of_deleted_region = ends[i]
            subsequence_1 = sequence_1[initial_start:start_of_deleted_region]
            subsequence_2 = sequence_2[initial_start:start_of_deleted_region]
            initial_start = end_of_deleted_region
            final_blocks.append((subsequence_1, subsequence_2))
        final_blocks.append((sequence_1[initial_start:], sequence_2[initial_start:]))
        return final_blocks


def single_param_null_model(w, div):
    '''
    The simple single parameter null model that describes
    the window spectrum under an assumption of only mutation
    and no transfer
    '''
    return np.exp(-div * w) * (div * w + 1)


def merge_intervals(intervals):
    all_intervals = []
    for j, interval in enumerate(intervals):
        end, start = interval
        if j == 0:
            current_interval = interval
        else:
            if intervals[j-1][1] <= end:
                current_interval = (current_interval[0], start)
            else:
                all_intervals.append(current_interval)
                current_interval = interval
    if len(all_intervals) > 0:
        if all_intervals[-1] != current_interval:
            all_intervals.append(current_interval)
    else:
        all_intervals.append(current_interval)
    return all_intervals
