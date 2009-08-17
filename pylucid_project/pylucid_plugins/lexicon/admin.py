# coding: utf-8

"""
    PyLucid.admin
    ~~~~~~~~~~~~~~

    Register models in django admin interface.

    Last commit info:
    ~~~~~~~~~~~~~~~~~
    $LastChangedDate$
    $Rev$
    $Author$

    :copyleft: 2008 by the PyLucid team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.
"""

from django.contrib import admin
from django.conf import settings
from django.contrib.auth.models import User, Permission
from django.contrib.auth.admin import UserAdmin

from reversion.admin import VersionAdmin

from pylucid.base_admin import BaseAdmin
from pylucid_admin.admin_site import pylucid_admin_site

from lexicon.models import LexiconEntry


class LexiconEntryAdmin(BaseAdmin, VersionAdmin):
    list_display = ("id", "term", "lang", "tags", "is_public", "view_on_site_link", "lastupdatetime", "lastupdateby")
    list_display_links = ("term", "tags",)
    list_filter = ("is_public", "lang", "createby", "lastupdateby",)
    date_hierarchy = 'lastupdatetime'
    search_fields = ("term", "tags", "content")

pylucid_admin_site.register(LexiconEntry, LexiconEntryAdmin)
