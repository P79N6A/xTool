# -*- coding: utf-8 -*-

from importlib import import_module


def import_string(dotted_path):
    """
    Import a dotted module path and return the attribute/class designated by the
    last name in the path. Raise ImportError if the import failed.
    """
    try:
        module_path, class_name = dotted_path.rsplit('.', 1)
    except ValueError:
        raise ImportError("{} doesn't look like a module path".format(dotted_path))

    module = import_module(module_path)

    try:
        # 返回模块中的类
        return getattr(module, class_name)
    except AttributeError as err:
        raise ImportError('Module "{}" does not define a "{}" attribute/class'.format(
            module_path, class_name)
        )
