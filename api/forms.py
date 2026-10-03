from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import ItemCarro, Maquinaria


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label='Nombre', max_length=100)
    last_name = forms.CharField(label='Apellido', max_length=100)
    email = forms.EmailField(label='Correo electrónico')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'


class MaquinariaForm(forms.ModelForm):
    class Meta:
        model = Maquinaria
        fields = ('nombre', 'categoria', 'descripcion', 'image_url', 'tarifa_diaria', 'tarifa_semanal',
                  'garantia', 'cantidad', 'activo')
        widgets = {'descripcion': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-check-input' if isinstance(field.widget, forms.CheckboxInput) else 'form-control'


class AgregarCarroForm(forms.ModelForm):
    class Meta:
        model = ItemCarro
        fields = ('cantidad',)


class ItemCarroForm(forms.ModelForm):
    class Meta:
        model = ItemCarro
        fields = ('cantidad', 'fecha_inicio', 'fecha_fin')
        widgets = {'fecha_inicio': forms.DateInput(attrs={'type': 'date'}), 'fecha_fin': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def clean(self):
        datos = super().clean()
        inicio, fin = datos.get('fecha_inicio'), datos.get('fecha_fin')
        if not inicio or not fin:
            raise forms.ValidationError('Debes indicar ambas fechas antes de continuar.')
        if fin <= inicio:
            self.add_error('fecha_fin', 'La fecha de término debe ser posterior al inicio.')
        return datos
