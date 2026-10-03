import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'drf.settings')
django.setup()

from api.models import Maquinaria


MAQUINARIAS = [
    {'nombre': 'Excavadora hidráulica 320', 'categoria': 'Excavación', 'descripcion': 'Equipo de alto rendimiento para excavaciones y movimiento de tierra.', 'image_url': 'https://upload.wikimedia.org/wikipedia/commons/d/d8/Caterpillar_330_excavator_on_a_pile_of_dirt.jpg', 'tarifa_diaria': 280000, 'tarifa_semanal': 1500000, 'garantia': 500000, 'cantidad': 3},
    {'nombre': 'Retroexcavadora 4x4', 'categoria': 'Excavación', 'descripcion': 'Versátil para excavación, carga y labores urbanas.', 'image_url': 'https://upload.wikimedia.org/wikipedia/commons/4/40/Caterpillar_backhoe_loader_at_construction_site_in_Sunnyvale%2C_back_view.jpg', 'tarifa_diaria': 220000, 'tarifa_semanal': 1200000, 'garantia': 400000, 'cantidad': 4},
    {'nombre': 'Grúa telescópica 25 t', 'categoria': 'Izaje', 'descripcion': 'Grúa móvil para maniobras de carga en obra.', 'image_url': 'https://upload.wikimedia.org/wikipedia/commons/f/f7/%D0%91%D0%B0%D0%BB%D1%85%D0%B0%D1%88%2C_%D0%9C%D0%90%D0%97-%D0%BA%D1%80%D0%B0%D0%BD_%D0%BD%D0%B0_%D0%96%D0%B5%D0%B7%D0%BA%D0%B0%D0%B7%D0%B3%D0%B0%D0%BD%D1%81%D0%BA%D0%BE%D0%B9.jpg', 'tarifa_diaria': 480000, 'tarifa_semanal': 2700000, 'garantia': 900000, 'cantidad': 2},
    {'nombre': 'Plataforma elevadora', 'categoria': 'Altura', 'descripcion': 'Plataforma articulada para trabajo seguro en altura.', 'image_url': 'https://upload.wikimedia.org/wikipedia/commons/6/6b/Articulating_Boom_Lift%2C_Stranraer_-_geograph.org.uk_-_7271692.jpg', 'tarifa_diaria': 190000, 'tarifa_semanal': 1000000, 'garantia': 350000, 'cantidad': 5},
    {'nombre': 'Rodillo compactador', 'categoria': 'Compactación', 'descripcion': 'Compactación eficiente de bases, caminos y pavimentos.', 'image_url': 'https://upload.wikimedia.org/wikipedia/commons/6/62/Caterpillar_CB54B_roller_on_dirt_lot_in_Campbell.jpg', 'tarifa_diaria': 240000, 'tarifa_semanal': 1300000, 'garantia': 420000, 'cantidad': 3},
    {'nombre': 'Generador industrial 100 kVA', 'categoria': 'Energía', 'descripcion': 'Suministro eléctrico estable para faenas y emergencias.', 'image_url': 'https://upload.wikimedia.org/wikipedia/commons/d/dc/Diesel_Generators.jpg', 'tarifa_diaria': 145000, 'tarifa_semanal': 760000, 'garantia': 250000, 'cantidad': 6},
]


def populate():
    for datos in MAQUINARIAS:
        maquinaria, creada = Maquinaria.objects.update_or_create(nombre=datos['nombre'], defaults=datos)
        print(f'{maquinaria.nombre}: {"creada" if creada else "actualizada"}')


if __name__ == '__main__':
    populate()
