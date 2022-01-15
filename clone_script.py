import logging
import os
import sys
import clone_repos as rh
import pathlib as path


def print_help():
    print(f'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]')
    print(f'    <assignment name>:'.ljust(25), 'Set assignment name. Same as repo prefix in organization')
    print(f'    <due date>:'.ljust(25), 'due date of assignment in yyyy-mm-dd format.')
    print(f'    <due time>:'.ljust(25), 'due time of assignment in HH:MM 24hr format.')
    print(f'    [folder name]:'.ljust(25), 'OPTIONAL. Changes output folder name from default assignment name')


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


def build_init_path_given_out(output_dir: path.Path, out_folder: str):
    init_path = output_dir / out_folder
    index = 1
    if path.Path(init_path).exists():
        new_path = path.Path(f'{init_path}_iter_{index}')
        while path.Path(new_path).exists():
            index += 1
            new_path = path.Path(f'{init_path}_iter_{index}')
        return path.Path(new_path)
    return path.Path(init_path)


def main(args, token = None, org = None, student_filename = None):
    '''
    Main function
    '''
    # Enable color in cmd
    if rh.is_windows():
        os.system('color')
    # Create log file
    logging.basicConfig(level=logging.INFO, filename=rh.LOG_FILE_PATH)

    # Try catch catches errors and sends them to the log file instead of outputting to console
    try:
        assignment_name, date_due, time_due, out_folder = parse_args(args)
        # Check local git version is compatible with script
        rh.check_git_version()
        # Check local PyGithub module version is compatible with script
        rh.check_pygithub_version()
        # Read config file, if doesn't exist make one using user input.
        if token != None and org != None and student_filename != None:
            _, _, _, output_dir = rh.read_config()
        else:
            token, org, student_filename, output_dir = rh.read_config()

        rh.check_update_available(token)

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

        # Print and log students that have not accepted assignment
        not_accepted = rh.find_students_not_accepted(students, repos, assignment_name)
        for student in not_accepted:
            print(f'{rh.LIGHT_RED}`{students[student]}` ({student}) did not accept the assignment.{rh.WHITE}')
            logging.info(f'{students[student]}` ({student}) did not accept the assignment `{assignment_name}` by the due date/time.')
        print()
            
        threads = []
        # goes through list of repos and clones them into the assignment's parent folder
        for repo in repos:
            # Create thread to handle repos and add to thread list
            # Each thread clones a repo, sets it back to due date/time, and gets avg lines per commit
            thread = rh.RepoHandler(repo, assignment_name, date_due, time_due, students, initial_path, token)
            threads += [thread]

        # Run all clone threads
        for thread in threads:
            thread.start()

        # Make main thread wait for all repos to be cloned, set back to due date/time, and avg lines per commit to be found
        for thread in threads:
            thread.join()

        num_of_lines = rh.write_avg_insersions_file(initial_path, assignment_name)
        rh.print_end_report(students, repos, len(not_accepted), rh.cloned_counter.value, rh.rollback_counter.value, num_of_lines)
    except Exception as e:
        logging.error(e)
        print() 
        try:
            print(f'{rh.LIGHT_RED}{e.message}{rh.WHITE}')
        except Exception:
            print(e)


if __name__ == '__main__':
    main(sys.argv)
