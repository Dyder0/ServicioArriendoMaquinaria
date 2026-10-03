from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import CarroArriendo, Contrato, ItemCarro, Maquinaria, PerfilUsuario, UnidadFlota
from .services import cambiar_estado_contrato, crear_contrato


class ArriendoBase(TestCase):
    def setUp(self):
        self.empresa = User.objects.create_user('empresa', password='Clave-segura-123')
        self.ejecutivo = User.objects.create_user('ejecutivo', password='Clave-segura-123', is_staff=True)
        self.maquina = Maquinaria.objects.create(
            nombre='Excavadora 320', categoria='Excavación', descripcion='Excavadora hidráulica',
            image_url='https://upload.wikimedia.org/wikipedia/commons/d/d8/Caterpillar_330_excavator_on_a_pile_of_dirt.jpg',
            tarifa_diaria=100000, tarifa_semanal=500000, garantia=200000, cantidad=2,
        )
        self.inicio = date.today() + timedelta(days=2)
        self.fin = self.inicio + timedelta(days=9)

    def crear_carro(self, usuario=None, cantidad=1, inicio=None, fin=None):
        carro = CarroArriendo.objects.create(usuario=usuario or self.empresa)
        ItemCarro.objects.create(
            carro=carro, maquinaria=self.maquina, cantidad=cantidad,
            fecha_inicio=inicio or self.inicio, fecha_fin=fin or self.fin,
        )
        return carro


class PrecioYContratoTests(ArriendoBase):
    def test_precio_semanal_dias_restantes_y_garantia(self):
        item = self.crear_carro(cantidad=2).items.get()
        self.assertEqual(item.subtotal_arriendo, 1400000)  # (1 semana + 2 días) × 2
        self.assertEqual(item.subtotal, 1800000)

    def test_checkout_crea_pendiente_y_vacia_carro(self):
        self.crear_carro()
        contrato = crear_contrato(self.empresa)
        self.assertEqual(contrato.estado, Contrato.PENDIENTE)
        self.assertEqual(contrato.items.count(), 1)
        self.assertFalse(self.empresa.carro_arriendo.items.exists())

    def test_pago_asigna_ids_fisicos_automaticamente(self):
        self.crear_carro(cantidad=2)
        contrato = crear_contrato(self.empresa)
        cambiar_estado_contrato(contrato.id, Contrato.PAGADO)
        item = contrato.items.get()
        self.assertEqual(item.unidades_asignadas.count(), 2)
        self.assertTrue(all(unidad.codigo.startswith('MQ-') for unidad in item.unidades_asignadas.all()))
        self.assertEqual(self.maquina.unidades_reservadas_activas, 2)
        self.assertEqual(self.maquina.disponibles_sin_reserva, 0)

    def test_mantenimiento_bloquea_la_unidad_al_pagar(self):
        unidad = self.maquina.unidades.first()
        unidad.estado = UnidadFlota.MANTENIMIENTO
        unidad.save(update_fields=('estado',))
        self.crear_carro(cantidad=2)
        contrato = crear_contrato(self.empresa)
        with self.assertRaises(ValueError):
            cambiar_estado_contrato(contrato.id, Contrato.PAGADO)

    def test_checkout_rechaza_item_sin_fechas(self):
        carro = CarroArriendo.objects.create(usuario=self.empresa)
        ItemCarro.objects.create(carro=carro, maquinaria=self.maquina, cantidad=1)
        with self.assertRaisesMessage(ValueError, 'fechas válidas'):
            crear_contrato(self.empresa)

    def test_checkout_rechaza_arriendo_para_el_mismo_dia(self):
        carro = CarroArriendo.objects.create(usuario=self.empresa)
        ItemCarro.objects.create(
            carro=carro, maquinaria=self.maquina, cantidad=1,
            fecha_inicio=date.today(), fecha_fin=date.today() + timedelta(days=1),
        )
        with self.assertRaisesMessage(ValueError, 'desde mañana'):
            crear_contrato(self.empresa)

    def test_pago_reserva_y_evitar_sobre_reserva(self):
        self.crear_carro(cantidad=2)
        primero = crear_contrato(self.empresa)
        cambiar_estado_contrato(primero.id, Contrato.PAGADO)

        otra = User.objects.create_user('otra', password='Clave-segura-123')
        self.crear_carro(otra, cantidad=1)
        segundo = crear_contrato(otra)
        with self.assertRaises(ValueError):
            cambiar_estado_contrato(segundo.id, Contrato.PAGADO)

    def test_exige_un_dia_completo_entre_entrega_y_nuevo_arriendo(self):
        self.crear_carro(cantidad=2)
        primero = crear_contrato(self.empresa)
        cambiar_estado_contrato(primero.id, Contrato.PAGADO)

        sin_margen = User.objects.create_user('sin_margen', password='Clave-segura-123')
        self.crear_carro(
            sin_margen, cantidad=1, inicio=self.fin + timedelta(days=1), fin=self.fin + timedelta(days=4)
        )
        contrato_sin_margen = crear_contrato(sin_margen)
        with self.assertRaisesMessage(ValueError, 'mantención'):
            cambiar_estado_contrato(contrato_sin_margen.id, Contrato.PAGADO)

        con_margen = User.objects.create_user('con_margen', password='Clave-segura-123')
        self.crear_carro(
            con_margen, cantidad=1, inicio=self.fin + timedelta(days=2), fin=self.fin + timedelta(days=5)
        )
        contrato_con_margen = crear_contrato(con_margen)
        cambiar_estado_contrato(contrato_con_margen.id, Contrato.PAGADO)
        contrato_con_margen.refresh_from_db()
        self.assertEqual(contrato_con_margen.estado, Contrato.PAGADO)

    def test_cancelar_libera_periodo(self):
        self.crear_carro(cantidad=2)
        primero = crear_contrato(self.empresa)
        cambiar_estado_contrato(primero.id, Contrato.PAGADO)
        cambiar_estado_contrato(primero.id, Contrato.CANCELADO)
        self.assertEqual(self.maquina.disponibilidad(self.inicio, self.fin), 2)
        self.assertEqual(self.maquina.disponibles_sin_reserva, 2)

    def test_completar_libera_periodo(self):
        self.crear_carro(cantidad=2)
        contrato = crear_contrato(self.empresa)
        for estado in (Contrato.PAGADO, Contrato.ENTREGADO, Contrato.COMPLETADO):
            cambiar_estado_contrato(contrato.id, estado)
        self.assertEqual(self.maquina.disponibilidad(self.inicio, self.fin), 2)


class APITests(ArriendoBase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def test_catalogo_es_publico_y_filtrable(self):
        respuesta = self.api.get('/api/maquinarias/', {'categoria': 'Excavación', 'precio_max': 110000})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data), 1)

    def test_jwt_contiene_rol(self):
        respuesta = self.api.post('/api/token/', {'username': 'empresa', 'password': 'Clave-segura-123'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['rol'], PerfilUsuario.EMPRESA)
        self.assertIn('access', respuesta.data)
        self.assertIn('refresh', respuesta.data)

    def test_empresa_no_puede_crear_maquinaria(self):
        self.api.force_authenticate(self.empresa)
        respuesta = self.api.post('/api/maquinarias/', {
            'nombre': 'Grúa', 'categoria': 'Izaje', 'descripcion': 'Grúa', 'tarifa_diaria': 1,
            'tarifa_semanal': 5, 'garantia': 1, 'cantidad': 1, 'activo': True,
        })
        self.assertEqual(respuesta.status_code, 403)

    def test_carro_api_persistente_por_usuario(self):
        self.api.force_authenticate(self.empresa)
        datos = {'maquinaria': self.maquina.id, 'cantidad': 1}
        self.assertEqual(self.api.post('/api/carro-arriendo/', datos, format='json').status_code, 201)
        respuesta = self.api.get('/api/carro-arriendo/')
        self.assertEqual(respuesta.data['items'][0]['cantidad'], 1)
        self.assertIsNone(respuesta.data['items'][0]['fecha_inicio'])

        item_id = respuesta.data['items'][0]['id']
        actualizada = self.api.patch('/api/carro-arriendo/', {
            'item_id': item_id, 'cantidad': 2, 'fecha_inicio': self.inicio, 'fecha_fin': self.fin,
        }, format='json')
        self.assertEqual(actualizada.status_code, 200)
        item = ItemCarro.objects.get(pk=item_id)
        self.assertEqual(item.fecha_inicio, self.inicio)
        self.assertEqual(item.subtotal, 1800000)

    def test_ejecutivo_actualiza_estado(self):
        self.crear_carro()
        contrato = crear_contrato(self.empresa)
        self.api.force_authenticate(self.ejecutivo)
        respuesta = self.api.patch(f'/api/contratos/{contrato.id}/estado/', {'estado': 'PAGADO'}, format='json')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['estado'], 'PAGADO')


class WebTests(ArriendoBase):
    def test_portada_publica_renderiza_catalogo_y_footer(self):
        respuesta = self.client.get(reverse('home'))
        self.assertContains(respuesta, self.maquina.nombre)
        self.assertContains(respuesta, f'src="{self.maquina.image_url}"')
        self.assertContains(respuesta, 'loading="lazy"')
        self.assertContains(respuesta, 'Año: 2026')

    def test_ejecutivo_accede_panel_y_admin_no_existe(self):
        self.client.force_login(self.ejecutivo)
        panel = self.client.get(reverse('panel'))
        self.assertEqual(panel.status_code, 200)
        self.assertContains(panel, 'Arrendadas hoy')
        self.assertContains(panel, 'OCUPACIÓN PROGRAMADA')
        self.assertEqual(self.client.get('/admin/').status_code, 404)

    def test_panel_muestra_unidades_arrendadas_y_disponibles(self):
        contrato = Contrato.objects.create(usuario=self.empresa, estado=Contrato.PAGADO, total=300000)
        item = contrato.items.create(
            maquinaria=self.maquina, maquinaria_nombre=self.maquina.nombre, cantidad=1,
            fecha_inicio=date.today() - timedelta(days=1), fecha_fin=date.today() + timedelta(days=2),
            tarifa_diaria=self.maquina.tarifa_diaria, tarifa_semanal=self.maquina.tarifa_semanal,
            garantia=self.maquina.garantia, subtotal=300000,
        )
        item.unidades_asignadas.add(self.maquina.unidades.first())
        self.client.force_login(self.ejecutivo)
        panel = self.client.get(reverse('panel'))
        maquina_panel = next(item for item in panel.context['maquinarias'] if item.id == self.maquina.id)
        self.assertEqual(maquina_panel.reservadas, 1)
        self.assertEqual(maquina_panel.arrendadas_hoy, 1)
        self.assertEqual(maquina_panel.disponibles_hoy, 1)
        self.assertContains(panel, 'Inicio')
        self.assertContains(panel, 'Entrega')

    def test_panel_muestra_revision_en_calendario(self):
        unidad = self.maquina.unidades.first()
        unidad.estado = UnidadFlota.REVISION
        unidad.save(update_fields=('estado',))
        self.client.force_login(self.ejecutivo)
        panel = self.client.get(reverse('panel'))
        self.assertContains(panel, unidad.codigo)
        self.assertContains(panel, 'Revisión')

    def test_flujo_fechas_se_guardan_en_carro_y_checkout(self):
        self.client.force_login(self.empresa)
        self.client.post(reverse('agregar_carro_web', args=(self.maquina.id,)), {'cantidad': 1})
        item = ItemCarro.objects.get(carro__usuario=self.empresa)
        self.assertIsNone(item.fecha_inicio)
        self.assertContains(self.client.get(reverse('carro_web')), 'type="date"')

        self.client.post(reverse('checkout_web'))
        self.assertFalse(Contrato.objects.exists())

        respuesta = self.client.post(reverse('actualizar_item_carro_web', args=(item.id,)), {
            'cantidad': 1, 'fecha_inicio': self.inicio.isoformat(), 'fecha_fin': self.fin.isoformat(),
        })
        self.assertRedirects(respuesta, reverse('carro_web'))
        item.refresh_from_db()
        self.assertEqual(item.fecha_fin, self.fin)
        recarga = self.client.get(reverse('carro_web'))
        self.assertContains(recarga, f'value="{self.inicio.isoformat()}"')
        self.assertContains(recarga, 'semana(s) a')

        self.client.post(reverse('checkout_web'))
        self.assertTrue(Contrato.objects.filter(usuario=self.empresa, estado=Contrato.PENDIENTE).exists())

    def test_carro_no_permite_solicitar_para_el_mismo_dia(self):
        self.client.force_login(self.empresa)
        self.client.post(reverse('agregar_carro_web', args=(self.maquina.id,)), {'cantidad': 1})
        item = ItemCarro.objects.get(carro__usuario=self.empresa)
        self.client.post(reverse('actualizar_item_carro_web', args=(item.id,)), {
            'cantidad': 1, 'fecha_inicio': date.today().isoformat(),
            'fecha_fin': (date.today() + timedelta(days=1)).isoformat(),
        })
        item.refresh_from_db()
        self.assertIsNone(item.fecha_inicio)
        pagina_carro = self.client.get(reverse('carro_web'))
        fecha_minima = (date.today() + timedelta(days=1)).isoformat()
        self.assertContains(pagina_carro, f'min="{fecha_minima}"', count=2)
        item_contexto = pagina_carro.context['items_carro'][0]
        dia_hoy = next(
            dia for semana in item_contexto.calendario_semanas for dia in semana if dia['fecha'] == date.today()
        )
        self.assertTrue(dia_hoy['no_disponible'])

    def test_carro_muestra_reserva_entrega_y_mantencion_no_disponibles(self):
        self.crear_carro(cantidad=2)
        contrato = crear_contrato(self.empresa)
        cambiar_estado_contrato(contrato.id, Contrato.PAGADO)
        ItemCarro.objects.create(carro=self.empresa.carro_arriendo, maquinaria=self.maquina, cantidad=1)
        self.client.force_login(self.empresa)
        carro = self.client.get(reverse('carro_web'))
        self.assertContains(carro, 'Reservado')
        self.assertContains(carro, 'Entrega')
        self.assertContains(carro, 'Mantención')
        self.assertContains(carro, 'No disponible')

    def test_catalogo_muestra_consultar_fechas_si_toda_la_flota_esta_reservada(self):
        self.crear_carro(cantidad=2)
        contrato = crear_contrato(self.empresa)
        cambiar_estado_contrato(contrato.id, Contrato.PAGADO)
        self.client.force_login(self.empresa)
        catalogo = self.client.get(reverse('home'))
        self.assertContains(catalogo, 'Consultar fechas')
        self.assertContains(catalogo, '0 sin reserva')
