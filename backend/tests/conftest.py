"""Tests explicitly opt into demo settings; production is validated separately."""
import os

os.environ['APP_MODE'] = 'demo'
