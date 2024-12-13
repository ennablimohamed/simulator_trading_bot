import argparse


def get_environment():
    parser = argparse.ArgumentParser()
    parser.add_argument('env', choices=['test', 'prod'])
    args = parser.parse_args()
    return args.env