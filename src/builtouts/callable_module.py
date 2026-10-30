import sys
import types


def callable_module(func: object):
    """a decorator that makes a module callable"""
    module_name = func.__module__
    module = sys.modules[module_name]

    class CallableModule(types.ModuleType):
        def __call__(self, *args, **kwargs):
            return func(*args, **kwargs)

    # Dynamically change the module's class to our callable subclass
    module.__class__ = CallableModule
    return func