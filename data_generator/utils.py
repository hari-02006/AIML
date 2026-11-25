import random
import datetime

def get_random_state(seed):
    random.seed(seed)
    return random

def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + datetime.timedelta(n)
