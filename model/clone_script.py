import asyncio
import logging
import os
import sys
import clone_repos as rh

from pathlib import Path


def print_help():
    print('Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]')
    print('    <assignment name>:'.ljust(25), 'Set assignment name. Same as repo prefix in organization')
    print('    <due date>:'.ljust(25), 'due date of assignment in yyyy-mm-dd format.')
    print('    <due time>:'.ljust(25), 'due time of assignment in HH:MM 24hr format.')
    print('    [folder name]:'.ljust(25), 'OPTIONAL. Changes output folder name from default assignment name')


def parse_args(args: list):
    if (len(args) < 4) or (args[1] == '-help' or args[1] == '-h' or args[1] == '-?' or args[1] == '?') or (len(args) > 5):
        print_help()
        raise rh.InvalidArguments()

    assignment_name = args[1]
    date_due = args[2]
    time_due = args[3]

    out_folder = ''

    if len(args) == 5:
        out_folder = args[4]

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


def main(args, token=None, org=None, student_filename=None):
    '''
    Main function
    '''
    # Enable color in cmd
    if rh.is_windows():
        os.system('color')
    # Create log file
    if not Path(rh.LOG_FILE_PATH).exists():
        open(rh.LOG_FILE_PATH, 'w').close()
    logging.basicConfig(level=logging.INFO, filename=rh.LOG_FILE_PATH)

    # Try catch catches errors and sends them to the log file instead of outputting to console
    try:
        assignment_name, date_due, time_due, out_folder = parse_args(args)
        # Check local git version is compatible with script
        rh.check_git_version()
        # Check local PyGithub module version is compatible with script
        rh.check_pygithub_version()
        # Read config file, if doesn't exist make one using user input.
        if token is not None and org is not None and student_filename is not None:
            _, _, _, output_dir = rh.read_config()
        else:
            token, org, student_filename, output_dir = rh.read_config()

        rh.check_and_print_updates(token)

        # Create Organization to access repos
        git_org_client = rh.attempt_make_client(token, org, student_filename, output_dir)
        org_repos = git_org_client.get_repos()

        students = dict() # student dict variable do be used im main scope
        repos = rh.get_repos(assignment_name, org_repos)
        if student_filename: # if classroom roster is specified use it
            students = rh.get_students(student_filename) # fill student dict
            repos = rh.get_repos_specified_students(repos, students, assignment_name)

        rh.check_time(time_due)
        rh.check_date(date_due)
        rh.check_assignment_name(repos)
        # Sets path to output directory inside assignment folder where repos will be cloned.
        # Makes parent folder for whole assignment.
        initial_path = rh.build_init_path(output_dir, assignment_name, date_due, time_due)

        if out_folder:
            initial_path = build_init_path_given_out(output_dir, out_folder)

        os.mkdir(initial_path)

        print()

        # Print and log students that have not accepted assignment
        not_accepted = rh.find_students_not_accepted(students, repos, assignment_name)
        for student in not_accepted:
            print(f'{rh.LIGHT_RED}`{students[student]}` ({student}) did not accept the assignment.{rh.WHITE}')
            logging.info(f'{students[student]}` ({student}) did not accept the assignment `{assignment_name}` by the due date/time.')
        print()

        cloned_repos = asyncio.Queue()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(rh.clone_all_repos(repos, initial_path, students, assignment_name, token, cloned_repos))

        print()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(rh.rollback_all_repos(cloned_repos, date_due, time_due))

        rh.print_end_report(students, repos, len(not_accepted), len(os.listdir(initial_path)))
        rh.extract_data_folder(initial_path)
    except Exception as e:
        logging.error(e)
        print()
        try:
            print(f'{rh.LIGHT_RED}{e.message}{rh.WHITE}')
        except Exception:
            print(e)


if __name__ == '__main__':
    main(sys.argv)