import yaml
from config.env_util import get_environment


def load_config(env):
    file_name = f'application-{env}.yml'
    with open(f'resources/{file_name}', 'r') as file:
        return yaml.safe_load(file)


def load_current_config():
    env = get_environment()
    file_name = f'application-{env}.yml'
    with open(f'resources/{file_name}', 'r') as file:
        return yaml.safe_load(file)
