import sys


def process_positions(filename):
    with open(filename, 'r') as file:
        interval = file.readlines()
    
    cleaned_list = [line.strip() for line in interval]
    
    tuple_list = [(int(start), int(end)) for start, end in [string.split('-') for string in cleaned_list]]

    pss_list = []
    for start, end in tuple_list:
        while start <= end:
            pss_list.append("A {} 99".format(start))
            start += 1

    return pss_list

def write_to_file(filename, results):
    with open(filename, 'w') as file:
        for i, result in enumerate(results):
            if i != len(results) - 1:
                file.write(result + '\n')
            else:
                file.write(result)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    results = process_positions(input_file)
    write_to_file(output_file, results)
