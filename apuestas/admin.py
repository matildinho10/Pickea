"""Registro de los modelos en el panel /admin/ para verlos y editarlos desde el navegador."""
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import Apuesta, Equipo, Mercado, Opcion, Partido, Temporada, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ['username', 'email', 'email_verificado', 'is_active', 'date_joined']
    list_filter = ['is_active', 'email_verificado', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (('Pronostika', {'fields': ['foto', 'email_verificado']}),)


@admin.register(Temporada)
class TemporadaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'anio', 'activa']


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'nombre_corto']


class MercadoInline(admin.TabularInline):
    model = Mercado
    extra = 0
    show_change_link = True


@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'temporada', 'fecha_numero', 'inicio', 'estado', 'marcador']
    list_filter = ['temporada', 'estado', 'fecha_numero']
    inlines = [MercadoInline]
    actions = ['fijar_cierre', 'liquidar']

    @admin.display(description='Marcador')
    def marcador(self, p):
        return '—' if p.goles_local is None else f'{p.goles_local}-{p.goles_visita}'

    @admin.action(description='Fijar cuotas de cierre')
    def fijar_cierre(self, request, queryset):
        for p in queryset:
            p.fijar_cuotas_cierre()
        self.message_user(request, 'Cuotas de cierre fijadas.')

    @admin.action(description='Liquidar según el resultado cargado')
    def liquidar(self, request, queryset):
        for p in queryset:
            try:
                p.liquidar()
            except Exception as e:
                self.message_user(request, f'{p}: {e}', messages.ERROR)


class OpcionInline(admin.TabularInline):
    model = Opcion
    extra = 0


@admin.register(Mercado)
class MercadoAdmin(admin.ModelAdmin):
    list_display = ['partido', 'tipo', 'es_principal', 'margen']
    list_filter = ['tipo']
    inlines = [OpcionInline]

    @admin.display(description='Margen')
    def margen(self, m):
        b = m.suma_inversas()
        return f'{(b - 1) * 100:.1f}%' if b else '—'


@admin.register(Apuesta)
class ApuestaAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'partido', 'opcion_etiqueta', 'unidades', 'cuota', 'cuota_cierre',
                    'resultado', 'ganancia', 'creada']
    list_filter = ['usuario', 'opcion__resultado']
    list_select_related = ['usuario', 'opcion__mercado__partido__local', 'opcion__mercado__partido__visita']
    # La cuota y el snapshot del mercado no se pueden tocar a mano: se fijan al confirmar.
    readonly_fields = ['cuota', 'cuotas_mercado', 'suma_inversas', 'creada']

    @admin.display(description='Opción')
    def opcion_etiqueta(self, a):
        return a.opcion.etiqueta

    @admin.display(description='Cierre')
    def cuota_cierre(self, a):
        return a.opcion.cuota_cierre

    @admin.display(description='Resultado')
    def resultado(self, a):
        return a.opcion.get_resultado_display()

    def has_add_permission(self, request):
        # Crear apuestas desde el admin saltaría la regla de la cuota vigente.
        return False
