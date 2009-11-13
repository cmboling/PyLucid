# coding: utf-8

"""
    PyLucid plugin tools
    ~~~~~~~~~~~~~~~~~~~~

    Last commit info:
    ~~~~~~~~~~~~~~~~~
    $LastChangedDate: $
    $Rev: $
    $Author: JensDiemer $

    :copyleft: 2009 by the PyLucid team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.p

"""

__version__ = "$Rev:$"

import re
import sys
import warnings

from django import http
from django.conf import settings
from django.template import loader
from django.http import HttpResponse
from django.core import urlresolvers
from django.utils.encoding import smart_str
from django.utils.importlib import import_module
from django.conf.urls.defaults import patterns, url

from pylucid.models import PluginPage, PageTree
from pylucid.system import pylucid_objects


from dbpreferences.forms import DBPreferencesBaseForm

class PyLucidDBPreferencesBaseForm(DBPreferencesBaseForm):
    def get_preferences(self, request, lucidtag_kwargs):
        """
        Update the preferences dict with the given kwargs dict.
        Send a staff user feedback if a kwargs key is invalid.
        """
        preferences = super(PyLucidDBPreferencesBaseForm, self).get_preferences()
        if request.user.is_staff:
            for key in lucidtag_kwargs.keys():
                if key not in preferences:
                    request.page_msg.info(
                        "Keyword argument %r is invalid for lucidTag %r !" % (key, self.Meta.app_label)
                    )
        preferences.update(lucidtag_kwargs)
        return preferences





class PluginGetResolver(object):
    def __init__(self, resolver):
        self.resolver = resolver
    def __call__(self, *args, **kwargs):
        return self.resolver

def _raise_resolve_error(plugin_url_resolver, rest_url):
    tried = [i[0][0][0] for i in plugin_url_resolver.reverse_dict.values()]
#    for key, value in plugin_url_resolver.reverse_dict.values():
#        print key, value

#    tried = [prefix + pattern.regex.pattern.lstrip("^") for pattern in plugin_urlpatterns]
    raise urlresolvers.Resolver404, {'tried': tried, 'path': rest_url + "XXX"}


def call_plugin(request, prefix_url, rest_url):
    """ Call a plugin and return the response. """
    lang_entry = request.PYLUCID.language_entry
    pluginpage = request.PYLUCID.pluginpage
    pagemeta = request.PYLUCID.pagemeta

    # build the url prefix
    url_prefix = "^%s/%s" % (pagemeta.language.code, prefix_url)

    # Get pylucid_project.system.pylucid_plugins instance
    plugin_instance = pluginpage.get_plugin()

    plugin_url_resolver = plugin_instance.get_plugin_url_resolver(
        url_prefix, urls_filename=pluginpage.urls_filename,
    )
    #for key, value in plugin_url_resolver.reverse_dict.items(): print key, value

    # get the plugin view from the complete url
    resolve_url = request.path_info
    result = plugin_url_resolver.resolve(resolve_url)
    if result == None:
        _raise_resolve_error(plugin_url_resolver, resolve_url)

    view_func, view_args, view_kwargs = result

    if "pylucid.views" in view_func.__module__:
        # The url is wrong, it's from PyLucid and we can get a loop!
        # FIXME: How can we better check, if the view is from the plugin and not from PyLucid???
        _raise_resolve_error(plugin_url_resolver, resolve_url)

    merged_url_resolver = plugin_instance.get_merged_url_resolver(
        url_prefix, urls_filename=pluginpage.urls_filename,
    )

    # Patch urlresolvers.get_resolver() function, so only our own resolver with urlpatterns2
    # is active in the plugin. So the plugin can build urls with normal django function and
    # this urls would be prefixed with the current PageTree url.
    old_get_resolver = urlresolvers.get_resolver
    urlresolvers.get_resolver = PluginGetResolver(merged_url_resolver)

    # Call the view
    response = view_func(request, *view_args, **view_kwargs)

    # restore the patched function
    urlresolvers.get_resolver = old_get_resolver

    return response


#______________________________________________________________________________
# ContextMiddleware functions

TAG_RE = re.compile("<!-- ContextMiddleware (.*?) -->", re.UNICODE)
from django.utils.importlib import import_module
from django.utils.functional import memoize

_middleware_class_cache = {}

def _get_middleware_class(plugin_name):
    plugin_name = plugin_name.encode('ascii') # check non-ASCII strings

    mod_name = "pylucid_plugins.%s.context_middleware" % plugin_name
    module = import_module(mod_name)
    middleware_class = getattr(module, "ContextMiddleware")
    return middleware_class
_get_middleware_class = memoize(_get_middleware_class, _middleware_class_cache, 1)


def context_middleware_request(request):
    """
    get from the template all context middleware plugins and call the request method.
    """
    context = request.PYLUCID.context
    context["context_middlewares"] = {}

    page_template = request.PYLUCID.page_template # page template content
    plugin_names = TAG_RE.findall(page_template)
    for plugin_name in plugin_names:
        # Get the middleware class from the plugin
        try:
            middleware_class = _get_middleware_class(plugin_name)
        except ImportError, err:
            request.page_msg.error("Can't import context middleware '%s': %s" % (plugin_name, err))
            continue

        # make a instance 
        instance = middleware_class(request, context)
        # Add it to the context
        context["context_middlewares"][plugin_name] = instance

def context_middleware_response(request, response):
    """
    replace the context middleware tags in the response, with the plugin render output
    """
    context = request.PYLUCID.context
    context_middlewares = context["context_middlewares"]
    def replace(match):
        plugin_name = match.group(1)
        try:
            middleware_class_instance = context_middlewares[plugin_name]
        except KeyError, err:
            return "[Error: context middleware %r doesn't exist!]" % plugin_name

        response = middleware_class_instance.render()
        if response == None:
            return ""
        elif isinstance(response, unicode):
            return smart_str(response, encoding=settings.DEFAULT_CHARSET)
        elif isinstance(response, str):
            return response
        elif isinstance(response, http.HttpResponse):
            return response.content
        else:
            raise RuntimeError(
                "plugin context middleware render() must return"
                " http.HttpResponse instance or a basestring or None!"
            )

    # FIXME: A HttpResponse allways convert unicode into string. So we need to do that here:
    # Or we say, context render should not return a HttpResponse?
#    from django.utils.encoding import smart_str
#    complete_page = smart_str(complete_page)

    source_content = response.content

    new_content = TAG_RE.sub(replace, source_content)
    response.content = new_content
    return response

