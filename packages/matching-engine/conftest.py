# conftest.py -- adds the matching-engine root to sys.path for pytest
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
