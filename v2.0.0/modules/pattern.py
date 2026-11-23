import sys
import re

def find_all_occurrences_re(text, pattern):
    
    matches = []
    for i in range(len(text)):
        match = re.match(pattern, text[i:])
        if match:
            matches.append((i, i + len(match.group()) - 1))

    seq_reversed = text[::-1]

    matches_reverse = []
    for i in range(len(seq_reversed)):
        match = re.match(pattern, seq_reversed[i:])
        if match:
            start, end = match.span()
            new_start = len(text) - (i + end)
            new_end = len(text) - (i + start + 1)
            matches_reverse.append((new_start, new_end))
    
    matches.extend(matches_reverse) 

    formatted_results = []
    for start, end in matches:
        formatted_results.append(f"{start + 1 }-{end +1}")
        
    unique_results = list(set(formatted_results))
    ordened_results = [tuple(map(int, intervalo.split('-'))) for intervalo in unique_results]
    ordened_results.sort()
    
    final = [f"{intervalo[0]}-{intervalo[1]}" for intervalo in ordened_results]

    return final

def write_positions_to_file(filename, results):
    with open(filename, 'w') as file:
        for result in results:
            file.write(result + '\n')

if __name__ == "__main__":
    print("Finding pattern")
    if len(sys.argv) != 4:
        sys.exit(1)

    pattern = sys.argv[1]
    seq = sys.argv[2]
    output_file = sys.argv[3]

    results = find_all_occurrences_re(seq, pattern)
    write_positions_to_file(output_file, results)

