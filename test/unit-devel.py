from apitest import TestBase,
#from apitest import TestBaseReadonly

"""
This module is used for testing new unit tests
When the test method is completted it is move som test-api.py

use 'nosetest -v -s unit-devel.py' to run the tests
"""

# class TestAPIDevel(TestBaseReadonly):


class TestAPIDevel(TestBase):

    def __init__(self, methodName='runTest'):
        super(TestAPIDevel, self).__init__(methodName)

