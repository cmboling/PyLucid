# -*- coding: utf-8 -*-

"""
    {% lucidTag ... %}
    ~~~~~~~~~~~~~~~~~~

    the special PyLucid tag who starts a plugin with the plugin manager.
    e.g.: {% lucidTag plugin_name.method_name key1="value1" key2="value2" %}

    registered in: ./PyLucid/defaulttags/__init__.py

    Last commit info:
    ~~~~~~~~~~~~~~~~~
    $LastChangedDate$
    $Rev$
    $Author$

    :copyleft: 2007 by the PyLucid team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.
"""

import re
import sys
import shlex

if __name__ == "__main__":
    # For doctest only
    import os
    os.environ["DJANGO_SETTINGS_MODULE"] = "django.conf.global_settings"

from django import template
from django.conf import settings
from django.http import HttpResponse

from pylucid.system import pylucid_plugin


# FIXME: The re should be more fault-tolerant:
KWARGS_REGEX = re.compile('''(\w*?)\=['"](.*?)['"]''')


# For str2dict()
KEYWORD_MAP = {
    "True": True,
    "False": False,
    "None": None,
}

def str2dict(raw_content):
    """
    convert a string into a dictionary. e.g.:

    >>> str2dict('key1="value1" key2="value2"')
    {'key2': 'value2', 'key1': 'value1'}

    >>> str2dict('A="B" C=1 D=1.1 E=True F=False G=None')
    {'A': 'B', 'C': 1, 'E': True, 'D': '1.1', 'G': None, 'F': False}
    
    >>> str2dict('''key1="'1'" key2='"2"' key3="""'3'""" ''')
    {'key3': 3, 'key2': 2, 'key1': 1}

    >>> str2dict(u'unicode=True')
    {'unicode': True}
    """
    if isinstance(raw_content, unicode):
        # shlex.split doesn't work with unicode?!?
        raw_content = raw_content.encode(settings.DEFAULT_CHARSET)

    parts = shlex.split(raw_content)

    result = {}
    for part in parts:
        key, value = part.split("=", 1)

        if value in KEYWORD_MAP:
            # True False or None
            value = KEYWORD_MAP[value]
        else:
            # A number?
            try:
                value = int(value.strip("'\""))
            except ValueError:
                pass

        result[key] = value

    return result



class lucidTagNodeError(template.Node):
    """
    display a error messages in the cms page for a wrong lucidTag.
    """
    def __init__(self, plugin_name, method_name, msg):
        self.plugin_name = plugin_name
        self.method_name = method_name
        self.msg = msg

    def render(self, context):
        return u"[lucidTag %s.%s syntax error: %s]" % (self.plugin_name, self.method_name, self.msg)


class lucidTagNode(template.Node):
    def __init__(self, raw_content, plugin_name, method_name, method_kwargs):
        self.raw_content = raw_content
        self.plugin_name = plugin_name
        self.method_name = method_name
        self.method_kwargs = method_kwargs

    def __repr__(self):
        return "<lucidTag node ('%s.%s' kwargs:%s)>" % (
            self.plugin_name, self.method_name, self.method_kwargs)

    def render(self, context):
        
        try:
            request = context["request"]
        except KeyError:
            raise KeyError("request object not in context! You must add it into the template context!")
        
        plugin_name = self.plugin_name
        method_name = self.method_name
        method_kwargs = self.method_kwargs
        
        try:
            response = pylucid_plugin.call_plugin_view(request, plugin_name, method_name, method_kwargs)
        except pylucid_plugin.GetCallableError, err:
            # FIXME:
            return u"[lucidTag %s.%s unknwon, error was: %s]" % (self.plugin_name, self.method_name, err)
        except:
            # insert more information into the traceback
            etype, evalue, etb = sys.exc_info()
            evalue = etype('Error rendering template tag "%s": %s' % (self.raw_content, evalue))
            raise etype, evalue, etb
        
        # FIXME: Witch error should we raised here?
        if response==None:
            return u""
        assert(isinstance(response, HttpResponse), "pylucid plugins must return a HttpResponse instance!")
        assert(response.status_code == 200, "Response status code != 200 ???")
        
        return response.content
#        
#        # callback is either a string like 'foo.views.news.stories.story_detail'
#        callback = "pylucid_plugins.%s.views.%s" % (self.plugin_name, self.method_name)
#        try:
#            callable = get_callable(callback)
#        except ImportError, err:
#
#        
#
#        
#        # Add info for pylucid_project.apps.pylucid.context_processors.pylucid
#        request.plugin_name = self.plugin_name
#        request.method_name = self.method_name
#        
#        try:
#            # call the plugin view method
#            response = callable(request, **self.method_kwargs)
#        except:
#
#        
#        # FIXME: Witch error should we raised here?
#        if response==None:
#            return u""
#        assert(isinstance(response, HttpResponse), "pylucid plugins must return a HttpResponse instance!")
#        assert(response.status_code == 200, "Response status code != 200 ???")
#        
#        return response.content




def lucidTag(parser, token):
    """
    Parse the lucidTags.

    syntax e.g.:
        {% lucidTag PluginName %}
        {% lucidTag PluginName kwarg1="value1" %}
        {% lucidTag PluginName kwarg1="value1" kwarg2="value2" %}
    """
    raw_content = token.contents
    content = raw_content.split(" ", 2)[1:]
    plugin_name = content.pop(0)

    if "." in plugin_name:
        plugin_name, method_name = plugin_name.split(".", 1)
    else:
        method_name = "lucidTag"

    if content:
        raw_kwargs = content[0]
        method_kwargs = str2dict(raw_kwargs)
    else:
        method_kwargs = {}

    return lucidTagNode(raw_content, plugin_name, method_name, method_kwargs)



if __name__ == "__main__":
    import doctest
    doctest.testmod(
#        verbose=True
        verbose=False
    )
    print "DocTest end."