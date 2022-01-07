import logging
import os
import sys

from clone_repos import RepoHandler, InvalidArguments, check_git_version, check_pygithub_version, read_config, MAX_THREADS, LOG_FILE_PATH, WHITE, LIGHT_GREEN, LIGHT_RED, write_avg_insersions_file, get_repos, get_students, get_repos_specified_students, build_init_path, is_windows, check_time, check_date, check_assignment_name, find_students_not_accepted, rollback_counter, cloned_counter
from github import Github
from pathlib import Path


def print_help():
    print(f'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]')
    print(f'    <assignment name>:'.ljust(25), 'Set assignment name. Same as repo prefix in organization')
    print(f'    <due date>:'.ljust(25), 'due date of assignment in yyyy-mm-dd format.')
    print(f'    <due time>:'.ljust(25), 'due time of assignment in HH:MM 24hr format.')
    print(f'    [folder name]:'.ljust(25), 'OPTIONAL. Changes output folder name from default assignment name')


def parse_args(args: list):
    if len(args) < 4:
        if len(args) > 1 and (args[1] == '-help' or args[1] == '-h' or args[1] == '-?' or args[1] == '?'):
            print_help()
            input('Press return key to exit...')
            exit()
        raise InvalidArguments()
    assignment_name = args[1]
    date_due = args[2]
    time_due = args[3]

    out_folder = ''

    if len(args) == 5:
        out_folder = args[4]

    if len(args) > 5:
        raise InvalidArguments()
        
    return assignment_name, date_due, time_due, out_folder


def build_init_path_given_out(output_dir: Path, out_folder: str):
    init_path = output_dir / out_folder
    index = 1
    if Path(init_path).exists():
        new_path = Path(f'{init_path}_iter_{index}')
        while Path(new_path).exists():
            index += 1
            new_path = Path(f'{init_path}_iter_{index}')
        return Path(new_path)
    return Path(init_path)


def main():
    '''
    Main function
    '''
    # Enable color in cmd
    if is_windows():
        os.system('color')
    # Create log file
    logging.basicConfig(level=logging.INFO, filename=LOG_FILE_PATH)

    # Try catch catches errors and sends them to the log file instead of outputting to console
    try:
        assignment_name, date_due, time_due, out_folder = parse_args(sys.argv)
        # Check local git version is compatible with script
        check_git_version()
        # Check local PyGithub module version is compatible with script
        check_pygithub_version()
        # Read config file, if doesn't exist make one using user input.
        token, organization, student_filename, output_dir = read_config()

        # Create Organization to access repos
        git_org_client = Github(token.strip(), pool_size = MAX_THREADS).get_organization(organization.strip())

        students = dict() # student dict variable do be used im main scope
        if student_filename: # if classroom roster is specified use it
            students = get_students(student_filename) # fill student dict
            repos = get_repos_specified_students(assignment_name, git_org_client, students)
        else:
            repos = get_repos(assignment_name, git_org_client)

        check_time(time_due)
        check_date(date_due)
        check_assignment_name(repos)
        # Sets path to output directory inside assignment folder where repos will be cloned.
        # Makes parent folder for whole assignment.
        initial_path = build_init_path(output_dir, assignment_name, date_due, time_due)  

        if out_folder:
            initial_path = build_init_path_given_out(output_dir, out_folder)
            
        os.mkdir(initial_path)

        # Print and log students that have not accepted assignment
        not_accepted = find_students_not_accepted(students, repos, assignment_name)
        for student in not_accepted:
            print(f'{LIGHT_RED}`{students[student]}` ({student}) did not accept the assignment.{WHITE}')
            logging.info(f'{students[student]}` ({student}) did not accept the assignment `{assignment_name}` by the due date/time.')
        print()
            
        threads = []
        # goes through list of repos and clones them into the assignment's parent folder
        for repo in repos:
            # Create thread to handle repos and add to thread list
            # Each thread clones a repo, sets it back to due date/time, and gets avg lines per commit
            thread = RepoHandler(repo, assignment_name, date_due, time_due, students, bool(student_filename), initial_path, token)
            threads += [thread]

        # Run all clone threads
        for thread in threads:
            thread.start()

        # Make main thread wait for all repos to be cloned, set back to due date/time, and avg lines per commit to be found
        for thread in threads:
            thread.join()

        num_of_lines = write_avg_insersions_file(initial_path, assignment_name)
        print()
        print(f'{LIGHT_GREEN}Done.{WHITE}')
        
        accept_str = f'{LIGHT_GREEN}{len(students)}{WHITE}' if len(not_accepted) == 0 else f'{LIGHT_RED}{len(students) - len(not_accepted)}{WHITE}'
        print(f'{LIGHT_GREEN}{accept_str}{LIGHT_GREEN}/{len(students)} accepted the assignment.{WHITE}')
        
        clone_str = f'{LIGHT_GREEN}{cloned_counter.value}{WHITE}' if cloned_counter.value == len(repos) else f'{LIGHT_RED}{cloned_counter.value}{WHITE}'
        print(f'{LIGHT_GREEN}Cloned {clone_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')
        
        rollback_str = f'{LIGHT_GREEN}{rollback_counter.value}{WHITE}' if rollback_counter.value == len(repos) else f'{LIGHT_RED}{rollback_counter.value}{WHITE}'
        print(f'{LIGHT_GREEN}Rolled Back {rollback_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')
        
        lines_str = f'{LIGHT_GREEN}{num_of_lines}{WHITE}' if num_of_lines == len(repos) else f'{LIGHT_RED}{num_of_lines}{WHITE}'
        print(f'{LIGHT_GREEN}Found average lines per commit for {lines_str}{LIGHT_GREEN}/{len(repos)} repos.{WHITE}')
    except Exception as e:
        logging.error(e)
        print() 
        try:
            print(f'{LIGHT_RED}{e.message}{WHITE}')
        except Exception:
            print(e)


if __name__ == '__main__':
    main()
