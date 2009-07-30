# coding:utf-8

from django.db import models
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.utils.translation import ugettext as _
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.managers import CurrentSiteManager

from pylucid.system.auto_model_info import UpdateInfoBaseModel
from pylucid.models import Language


class UpdateJournal(models.Model):
    """ List of all last update data, used for creating the last update table. """
    lastupdatetime = models.DateTimeField(auto_now=True, help_text="Time of the last change.",)
    user_name = models.CharField(_("user's name"), max_length=50, blank=True)

    site = models.ForeignKey(Site, default=Site.objects.get_current)
    on_site = CurrentSiteManager()

    # Content-object field
    content_type = models.ForeignKey(
        ContentType, verbose_name=_('content type'), related_name="content_type_set_for_%(class)s"
    )
    object_url = models.URLField(verbose_name=_('object url'), help_text="absolute url to the item.",)

    lang = models.ForeignKey(Language)

    title = models.CharField(blank=True, max_length=256,
        help_text="A long page title (for e.g. page title or link title text)"
    )
    staff_only = models.BooleanField(help_text="Viewable only by staff users?")

    class Meta:
        verbose_name = 'Update Journal entry'
        verbose_name_plural = 'Update Journal entries'
        ordering = ("-lastupdatetime",)


class PageUpdateListObjectsManager(models.Manager):
    def add_entry(self, model_instance):
        """ Add a new update journal entry. Called by signal handler page_update_list.save_receiver """
        update_info = model_instance.get_update_info()
        if update_info == None:
            # This entry should not be inserted in the update journal
            return

        # delete same entries
        object_url = update_info["object_url"]
        UpdateJournal.on_site.all().filter(object_url=object_url).delete()

        if isinstance(update_info["user_name"], User):
            user = update_info["user_name"]
            user_name = user.get_full_name() or user.username
            update_info["user_name"] = user_name

        content_type = ContentType.objects.get_for_model(model_instance)
        instance, created = PageUpdateListObjects.on_site.get_or_create(content_type=content_type)
        update_info.update({
            "staff_only": instance.staff_only,
            "content_type": content_type,
        })
        UpdateJournal(**update_info).save()


class PageUpdateListObjects(UpdateInfoBaseModel):
    """ Witch objects should be listed in the last update table? """
    objects = PageUpdateListObjectsManager()

    site = models.ForeignKey(Site, default=Site.objects.get_current)
    on_site = CurrentSiteManager()

    content_type = models.ForeignKey(
        ContentType, verbose_name=_('content type'), related_name="content_type_set_for_%(class)s"
    )
    staff_only = models.BooleanField(default=False, help_text="Viewable only by staff users?")
