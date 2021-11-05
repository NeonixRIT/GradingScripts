import logging
import os
import sys

from cloneRepositories import RepoHandler, check_git_version, check_pygithub_version, read_config, MAX_THREADS, LOG_FILE_PATH, WHITE, LIGHT_GREEN, write_avg_insersions_file, get_repos, get_students, get_repos_specified_students, file_exists_handler
from github import Github


def print_help():
    print(f'Usage: ./cloneScript.py <assignment name> <due date> <due time> [folder name]')
    print(f'    <assignment name>:'.ljust(25), 'Set assignment name. Same as repo prefix in organization')
    print(f'    <due date>:'.ljust(25), 'due date of assignment in yyyy-mm-dd format.')
    print(f'    <due time>:'.ljust(25), 'due time of assignment in HH:MM 24hr format.')
    print(f'    [folder name]:'.ljust(25), 'OPTIONAL. Changes output folder name from default assignment name')


def main():
    # Enable color in cmd
    if os.name == 'nt':
        os.system('color')
    # Create log file
    logging.basicConfig(level=logging.INFO, filename=LOG_FILE_PATH)

    args = sys.argv
    try:
        if len(args) < 4:
            if len(args) > 1 and (args[1] == '-help' or args[1] == '-h'):
                print_help()
                input('Press return key to exit...')
                exit()
            raise ValueError('invalid number of arguments')
        script_name = args[0]
        assignment_name = args[1]
        date_due = args[2]
        time_due = args[3]

        out_folder = ''

        if len(args) == 5:
            out_folder = args[4]

        if len(args) > 5:
            raise ValueError('invalid number of arguments')

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

        # Sets path to output directory inside assignment folder where repos will be cloned
        initial_path = output_dir / assignment_name

        if out_folder:
            initial_path = output_dir / out_folder

        # Makes parent folder for whole assignment. Raises eror if file already exists and it cannot be deleted
        file_exists_handler(initial_path)

        threads = []
        # goes through list of repos and clones them into the assignment's parent folder
        for repo in repos:
            # Create thread to handle repos and add to thread list
            # Each thread clones a repo, sets it back to due date/time, and gets avg lines per commit
            thread = RepoHandler(repo, assignment_name, date_due, time_due, students, bool(student_filename), initial_path)
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
        print(f'{LIGHT_GREEN}Cloned {len(next(os.walk(initial_path))[1])}/{len(repos)} repos.{WHITE}')
        print(f'{LIGHT_GREEN}Found average lines per commit for {num_of_lines}/{len(repos)} repos.{WHITE}')
    except FileNotFoundError as e: # If classroom roster file specified in config.txt isn't found.
        print()
        print(f'Classroom roster `{student_filename}` not found.')
        logging.error(e)
    except FileExistsError as e: # Error thrown if parent assignment file already exists
        print()
        print(f'ERROR: File `{initial_path}` already exists, please delete it and run again')
        logging.error(e)
    except KeyboardInterrupt as e: # When thread fails because subprocess command threw some error/exception
        print()
        print('ERROR: Something happened during the cloning process; your repos are not at the proper timestamp. Delete the assignment folder and run again.')
        logging.error(e)
    except ValueError as e: # When git version is incompatible w/ script
        print()
        print(e)
        logging.error(e)
    except NotImplementedError as e:
        print()
        print(e)
        logging.error(e)
    except Exception as e: # If anything else happens
        print(f'ERROR: Something happened. Check {LOG_FILE_PATH}')
        logging.error(e)
    input('Press return key to exit...')
    exit()


if __name__ == '__main__':
    main()
