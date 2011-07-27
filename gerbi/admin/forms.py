# -*- coding: utf-8 -*-
"""Page CMS forms"""
from django import forms
from django.template.defaultfilters import slugify
from django.utils.translation import ugettext_lazy as _
from django.utils.encoding import force_unicode
from django.conf import global_settings

from gerbi.utils import get_placeholders
from gerbi import settings
from gerbi.models import Page, Content
from gerbi.urlconf_registry import get_choices
from gerbi.widgets import LanguageChoiceWidget
from gerbi.templatetags.gerbi_tags import get_page_from_string_or_id

# error messages
default_slug_required = _('Every page need a slug in the default language')
another_page_error = _('Another page with this slug already exists')
sibling_position_error = _('A sibling with this slug already exists at the \
targeted position')
child_error = _('A child with this slug already exists at the targeted \
position')
sibling_error = _('A sibling with this slug already exists')
sibling_root_error = _('A sibling with this slug already exists at the root \
level')

class PageForm(forms.ModelForm):
    """Form for page creation"""

    title = forms.CharField(
        label=_('Title'),
        widget=forms.Textarea,
    )
    slug = forms.CharField(
        required=False,
        label=_('Slug'),
        widget=forms.TextInput(),
        help_text=_('The slug will be used to create the page URL, \
it must be unique among the other pages of the same level.')
    )
    language = forms.ChoiceField(
        label=_('Language'),
        choices=settings.GERBI_LANGUAGES,
        widget=LanguageChoiceWidget()
    )
    template = forms.ChoiceField(
        required=False,
        label=_('Template'),
        choices=settings.get_page_templates(),
    )
    delegate_to = forms.ChoiceField(
        required=False,
        label=_('Delegate to application'),
        choices=get_choices(),
    )
    freeze_date = forms.DateTimeField(
        required=False,
        label=_('Freeze'),
        help_text=_("Don't publish any content after this date. Format is 'Y-m-d H:M:S'")
        # those make tests fail miserably
        #widget=widgets.AdminSplitDateTime()
        #widget=widgets.AdminTimeWidget()
    )

    redirect_to = forms.IntegerField(
        label=_('Redirect to'),
        widget=forms.TextInput(),
        help_text=_('Input the id of the page'),
        required=False
    )

    target = forms.IntegerField(required=False, widget=forms.HiddenInput)
    position = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Page

    def __init__(self, *args, **kwargs):

        language = kwargs.pop('language')
        self.language = language
        template = kwargs.pop('template')
        page = kwargs.get('instance')

        super(PageForm, self).__init__(*args, **kwargs)

        del self.fields['author']
        del self.fields['last_modification_date']

        self.fields['language'].initial = language
        self.fields['language'].widget = LanguageChoiceWidget(page=page, language=language)

        if settings.GERBI_USE_SITE_ID:
            self.fields['sites'].initial = [settings.SITE_ID]

        if page:
            initial_slug = page.slug(language=language, fallback=False)
            initial_title = page.title(language=language, fallback=False)
            self.fields['slug'].initial = initial_slug
            self.fields['title'].initial = initial_title
            #form.fields['slug'].label = _('Slug')

        page_templates = settings.get_page_templates()
        if len(page_templates) > 0:
            template_choices = list(page_templates)
            template_choices.insert(0, (settings.GERBI_DEFAULT_TEMPLATE,
                    _('Default template')))
            self.fields['template'].choices = template_choices
            self.fields['template'].initial = force_unicode(template)

        for placeholder in get_placeholders(template):
            name = placeholder.name
            if page:
                initial = placeholder.get_content(page, language, name)
            else:
                initial = None
            self.fields[name] = placeholder.get_field(page, language,
                initial=initial)

    def clean_slug(self):
        """Handle slug of the page"""

        slug = slugify(self.cleaned_data['slug'].strip())

        if self.language == settings.GERBI_DEFAULT_LANGUAGE:
            if not len(slug):
                raise forms.ValidationError(default_slug_required)
        else:
            if not Content.objects.filter(page=self.instance, type="slug").count():
                raise forms.ValidationError(default_slug_required)

        target = self.data.get('target', None)
        position = self.data.get('position', None)

        if settings.GERBI_UNIQUE_SLUG_REQUIRED:
            if self.instance.id:
                if Content.objects.exclude(page=self.instance).filter(
                    body=slug, type="slug").count():
                    raise forms.ValidationError(another_page_error)
            elif Content.objects.filter(body=slug, type="slug").count():
                raise forms.ValidationError(another_page_error)

        if settings.GERBI_USE_SITE_ID:
            if settings.GERBI_HIDE_SITES:
                site_ids = [settings.SITE_ID]
            else:
                site_ids = [int(x) for x in self.data.getlist('sites')]
            def intersects_sites(sibling):
                return sibling.sites.filter(id__in=site_ids).count() > 0
        else:
            def intersects_sites(sibling):
                return True

        if not settings.GERBI_UNIQUE_SLUG_REQUIRED:
            if target and position:
                target = Page.objects.get(pk=target)
                if position in ['right', 'left']:
                    slugs = [sibling.slug() for sibling in
                             target.get_siblings()
                             if intersects_sites(sibling)]
                    slugs.append(target.slug())
                    if slug in slugs:
                        raise forms.ValidationError(sibling_position_error)
                if position == 'first-child':
                    if slug in [sibling.slug() for sibling in
                                target.get_children()
                                if intersects_sites(sibling)]:
                        raise forms.ValidationError(child_error)
            else:
                if self.instance.id:
                    if (slug in [sibling.slug() for sibling in
                        self.instance.get_siblings().exclude(
                            id=self.instance.id
                        ) if intersects_sites(sibling)]):
                        raise forms.ValidationError(sibling_error)
                else:
                    if slug in [sibling.slug() for sibling in
                                Page.objects.root()
                                if intersects_sites(sibling)]:
                        raise forms.ValidationError(sibling_root_error)
        return slug