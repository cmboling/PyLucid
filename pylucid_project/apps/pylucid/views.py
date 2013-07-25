# coding:utf-8

"""
    PyLucid
    ~~~~~~~

    :copyleft: 2009-2013 by the PyLucid team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.
"""


from django import http
from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.template import loader, RequestContext
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_exempt

from django_tools.template import render

from pylucid_project.apps.pylucid.markup.converter import apply_markup
from pylucid_project.apps.pylucid.models import PageTree, PageMeta, \
        PageContent, PluginPage, ColorScheme, EditableHtmlHeadFile, Language
from pylucid_project.apps.pylucid.signals import pre_render_global_template
from pylucid_project.apps.pylucid.system import pylucid_plugin, i18n
from pylucid_project.system.pylucid_plugins import PYLUCID_PLUGINS
from django.template.loader import render_to_string
from pylucid_project.apps.pylucid.decorators import pylucid_objects




# _____________________________________________________________________________
# helper functions

def _get_page_content(request):
    """
    Returns the PageContent instance for the current pagetree:
    Try in client favored language, if not exist...
    ...try in default language set in the system preferences, if not exist...
    ...raise http.Http404()
    """
    pagetree = request.PYLUCID.pagetree  # current PageTree instance
    pagemeta = request.PYLUCID.pagemeta  # current PageMeta instance

    # client favored Language instance:
    lang_entry = request.PYLUCID.current_language
    # default Language instance set in system preferences:
    default_lang_entry = Language.objects.get_or_create_default(request)

    try:
        pagecontent = PageContent.objects.get(pagemeta=pagemeta)
    except PageContent.DoesNotExist, err:
        raise http.Http404(
            "Page '%s' does not exist in default language '%s'.\n"
            "Original error was: %s" % (
                pagetree.slug, default_lang_entry.code, err
            )
        )

    return pagecontent


def _render_page(request):
    """ render a cms page """
    path_info = request.PYLUCID.path_info
    url_lang_code = path_info.url_lang_code
    prefix_url = path_info.prefix_url
    rest_url = path_info.rest_url

    pagetree = request.PYLUCID.pagetree
    pagemeta = request.PYLUCID.pagemeta

    is_plugin_page = pagetree.page_type == PageTree.PLUGIN_TYPE
    if is_plugin_page:
        print "is plugin page:", url_lang_code, prefix_url, rest_url

    # Create initial context object
    context = request.PYLUCID.context = RequestContext(request)

    # it will be filled either by plugin or by PageContent:
    context["page_content"] = None

    # call a pylucid plugin "html get view", if exist
    get_view_response = PYLUCID_PLUGINS.call_get_views(request)
    if isinstance(get_view_response, http.HttpResponse):
        # Plugin would be build the complete html page
        return get_view_response
    elif isinstance(get_view_response, basestring):
        # Plugin replace the page content
        context["page_content"] = get_view_response
    elif get_view_response is not None:  # Use plugin response
        raise TypeError(
            "Plugin view must return None or basestring or HttpResponse! (returned: %r)"
        ) % type(get_view_response)

    if context["page_content"] is None:
        # Plugin has not filled the page content
        pagecontent_instance = _get_page_content(request)
        request.PYLUCID.pagecontent = request.PYLUCID.updateinfo_object = pagecontent_instance
        context["page_content"] = apply_markup(
            pagecontent_instance.content, pagecontent_instance.markup, request
        )

    # put update information into context
    for itemname in ("createby", "lastupdateby", "createtime", "lastupdatetime"):
        context["page_%s" % itemname] = getattr(request.PYLUCID.updateinfo_object, itemname, None)

    # Render django tags in PageContent with the global context
    context["page_content"] = render.render_string_template(context["page_content"], context)

    template_name = context["base_template_name"]  # Added in pylucid.context_processors
    page_template = loader.get_template(template_name)
    pre_render_global_template.send(sender=None, request=request, page_template=page_template)

    # Render django tags in global template with global context
    complete_page = page_template.render(context)

    # create response object
    response = http.HttpResponse(complete_page, mimetype="text/html")
    response["content-language"] = context["page_language"]

    return response








# _____________________________________________________________________________
# view functions

def send_head_file(request, filepath):
    """
    Sending a headfile
    only a fall-back method if the file can't be stored into the media path
    """
    colorscheme = None
    if "ColorScheme" in request.GET:
        raw_colorscheme_id = request.GET["ColorScheme"]
        try:
            colorscheme_id = int(raw_colorscheme_id)
        except ValueError:
            if settings.DEBUG:
                raise
            return http.HttpResponseBadRequest()

        try:
            colorscheme = ColorScheme.objects.get(pk=colorscheme_id)
        except ColorScheme.DoesNotExist:
            if settings.DEBUG:
                msg = "ColorScheme %r not found!" % colorscheme_id
            else:
                msg = ""
            raise http.Http404(msg)

    try:
        headfile = EditableHtmlHeadFile.objects.get(filepath=filepath)
    except EditableHtmlHeadFile.DoesNotExist:
        if settings.DEBUG:
            msg = "Headfile %r not found!" % filepath
        else:
            msg = ""
        raise http.Http404(msg)

    if headfile.render and colorscheme is not None:
        content = headfile.get_rendered(colorscheme)
    else:
        content = headfile.content

    mimetype = headfile.mimetype
    return http.HttpResponse(content, mimetype=mimetype)



def _prepage_request(request, lang_entry):
    """
    shared function for serval views.
    *
    """
    # setup i18n language settings
    i18n.setup_language(request, lang_entry)

# _____________________________________________________________________________
# root_page + lang_root_page views:

def _get_root_page(request):
    user = request.user
    try:
        pagetree = PageTree.objects.get_root_page(user)  # Get the first PageTree entry
    except PageTree.DoesNotExist, err:
        msg = _(
            "There exist no pages!"
            " Have you load the initial pylucid.json data file?"
            " At least there must exists one page!"
            " (original error was: %s)"
        ) % err
        raise http.Http404(msg)
    return pagetree


@csrf_exempt
def root_page(request):
    """
    redirect to a url with language code
    We can't serve the root page here, because it will be cached in current
    language with "/" as key. So a other client with other language will see
    the page always in the cached language and not in his preferred language
    """
    # activate language via auto detection
    i18n.activate_auto_language(request)

    pagetree = _get_root_page(request)

    pagemeta = PageTree.objects.get_pagemeta(request, pagetree, show_lang_errors=False)
    url = pagemeta.get_absolute_url()

    return http.HttpResponseRedirect(url)


def _lang_code_is_pagetree(request, url_lang_code):
    """
    return True, if language code...
        ... is not in settings.LANGUAGES
    and
        ... is a pagetree slug
    """
    if Language.objects.is_language_code(url_lang_code) == True:
        # It's a valid language code
        return False

    # Check if url language code is a pagetree slug
    exist = PageTree.on_site.filter(slug=url_lang_code).count()
    if exist > 0:
        return True

    return False


@csrf_exempt
def lang_root_page(request, url_lang_code):
    """ url with lang code but no page slug """

    if _lang_code_is_pagetree(request, url_lang_code):
        # The url doesn't contain a language code, it's a pagetree slug
        return _i18n_redirect(request, url_path=url_lang_code)

    return root_page(request)


#-----------------------------------------------------------------------------

def _i18n_redirect(request, url_path):
    """ Redirect to a url with the default language code. """
    # activate language via auto detection
    i18n.activate_auto_language(request)

    # Check only, if url_path is right (if there exist a pagetree object)
    # otherwise -> 404 would be raised
    try:
        PageTree.objects.get_page_from_url(request, url_path)
    except PageTree.DoesNotExist, err:
        msg = _("Page not found")
        if settings.DEBUG or request.user.is_staff:
            msg += " url path: %r (%s)" % (url_path, err)
        raise http.Http404(msg)

    lang_code = request.LANGUAGE_CODE
    url = reverse('PyLucid-resolve_url', kwargs={'url_lang_code': lang_code, 'url_path': url_path})

    if not url.endswith("/"):
        url += "/"

    if request.GET:
        # Add GET query string
        # We don't use request.GET.urlencode() here, because it can change the key positions
        full_path = request.get_full_path()
        get_string = full_path.split("?", 1)[1]
        url += "?" + get_string

    # redirect to url with lang_code
    return http.HttpResponseRedirect(url)




# We must exempt csrf test here, but we use csrf_protect() later in:
# pylucid_project.apps.pylucid.system.pylucid_plugin.call_plugin()
# pylucid_project.system.pylucid_plugins.PyLucidPlugin.call_plugin_view()
# see also: https://docs.djangoproject.com/en/dev/ref/contrib/csrf/#view-needs-protection-for-one-path
@pylucid_objects  # create request.PYLUCID
@csrf_exempt
def resolve_url(request, url_lang_code, url_path):
    """ url with lang_code and sub page path """
    if _lang_code_is_pagetree(request, url_lang_code):
        # url_lang_code doesn't contain a language code, it's a pagetree slug
        new_url = "%s/%s" % (url_lang_code, url_path)
        return _i18n_redirect(request, url_path=new_url)

    # activate language via auto detection
    i18n.activate_auto_language(request)

    request.PYLUCID.path_info.url_lang_code = url_lang_code
    return _render_page(request)


def page_without_lang(request, url_path):
    """
    url with sub page path, but without a lang_code part
    We redirect to a url with language code.
    """
    # redirect to a url with the default language code.
    return _i18n_redirect(request, url_path)


@csrf_exempt
def permalink(request, page_id, url_rest=""):
    """ resolve a permalink and redirect to the real url. """
    # activate language via auto detection
    i18n.activate_auto_language(request)

    try:
        pagetree = PageTree.on_site.get(id=page_id)
    except PageTree.DoesNotExist, err:
        # TODO: Try to search with the additional url data (url_rest)
        msg = "Page not found"
        if settings.DEBUG:
            msg += " PageTree ID: %r (%s)" % (page_id, err)
        raise http.Http404(msg)

    pagemeta = PageTree.objects.get_pagemeta(request, pagetree, show_lang_errors=False)

    url = pagemeta.get_absolute_url()

    if pagetree.page_type == pagetree.PLUGIN_TYPE and url_rest and "/" in url_rest:
        # pass a permalink additional to the plugin, e.g.: blog entry detail view
        additional_url = url_rest.split("/", 1)[1]
        url += additional_url

    return http.HttpResponseRedirect(url)




