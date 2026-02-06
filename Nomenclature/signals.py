from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import GlobalProductAttribute, Nomenclature

@receiver(post_delete, sender=GlobalProductAttribute)
def remove_attribute_from_products(sender, instance, **kwargs):
    """
    Removes the attribute key from the extra_data field of all Nomenclature records
    when a GlobalProductAttribute is deleted.
    """
    # This is a bit expensive if there are many records, but necessary for data consistency.
    # Ideally, this would be done in a background task (Celery).
    # For now, we'll do it synchronously as per the requirement.
    
    # We need to iterate because JSONField key removal isn't straightforward in all DB backends 
    # with a single update query without raw SQL or specific functions.
    # Using python loop for cross-db compatibility and simplicity for now.
    
    products = Nomenclature.objects.filter(extra_data__has_key=instance.name)
    for product in products:
        if instance.name in product.extra_data:
            del product.extra_data[instance.name]
            product.save(update_fields=['extra_data'])
