import json

from django.db import migrations


def _coerce(raw):
    """Best-effort: decode a possibly double-encoded structure into a real object.

    Repeatedly json.loads while the result is still a string. Returns (value, changed).
    """
    if not isinstance(raw, str):
        return raw, False

    current = raw
    changed = False
    # Guard against pathological inputs.
    for _ in range(5):
        try:
            decoded = json.loads(current)
        except (ValueError, TypeError):
            break
        changed = True
        if isinstance(decoded, str):
            current = decoded
            continue
        return decoded, changed

    # Could not decode to a non-string object; leave as-is.
    return raw, False


def convert_structures(apps, schema_editor):
    BarcodeTemplate = apps.get_model('BarcodeTemplates', 'BarcodeTemplate')
    for template in BarcodeTemplate.objects.all():
        new_value, changed = _coerce(template.structure)
        if changed and not isinstance(new_value, str):
            template.structure = new_value
            template.save(update_fields=['structure'])


def noop_reverse(apps, schema_editor):
    # Converting objects back to double-encoded strings is intentionally not performed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('BarcodeTemplates', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(convert_structures, noop_reverse),
    ]
