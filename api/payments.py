"""Configuración y validaciones de la pasarela Webpay Plus."""

from decimal import Decimal

from django.conf import settings

from transbank.common.integration_api_keys import IntegrationApiKeys
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.common.integration_type import IntegrationType
from transbank.common.options import WebpayOptions
from transbank.webpay.webpay_plus.transaction import Transaction


def obtener_transaccion_webpay():
    """Crea el cliente oficial para integración o producción."""
    ambiente = settings.WEBPAY_ENVIRONMENT
    if ambiente == 'production':
        if not settings.WEBPAY_COMMERCE_CODE or not settings.WEBPAY_API_KEY:
            raise ValueError('Faltan WEBPAY_COMMERCE_CODE y WEBPAY_API_KEY para producción.')
        opciones = WebpayOptions(
            settings.WEBPAY_COMMERCE_CODE,
            settings.WEBPAY_API_KEY,
            IntegrationType.LIVE,
        )
    elif ambiente == 'integration':
        opciones = WebpayOptions(
            IntegrationCommerceCodes.WEBPAY_PLUS,
            IntegrationApiKeys.WEBPAY,
            IntegrationType.TEST,
        )
    else:
        raise ValueError('WEBPAY_ENVIRONMENT debe ser integration o production.')
    return Transaction(opciones)


def respuesta_autorizada(respuesta, pago):
    """Valida resultado, monto y referencias antes de confirmar la reserva."""
    try:
        monto_recibido = Decimal(str(respuesta.get('amount')))
        codigo_respuesta = int(respuesta.get('response_code'))
    except (TypeError, ValueError, ArithmeticError):
        return False
    return (
        respuesta.get('status') == 'AUTHORIZED'
        and codigo_respuesta == 0
        and monto_recibido == pago.monto
        and respuesta.get('buy_order') == pago.buy_order
        and respuesta.get('session_id') == pago.session_id
    )


def respuesta_segura(respuesta):
    """Retiene solo datos operativos; nunca persiste PAN, CVV ni secretos."""
    campos = (
        'amount', 'status', 'buy_order', 'session_id', 'accounting_date',
        'transaction_date', 'authorization_code', 'payment_type_code',
        'response_code', 'installments_number',
    )
    return {campo: respuesta.get(campo) for campo in campos if campo in respuesta}
