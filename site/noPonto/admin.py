from django.contrib import admin

# Register your models here.

from noPonto.models import Restaurante, Cardapio, Prato, Aluno, Avaliacao, EstiloComida, Mapa

admin.site.register(Restaurante)
admin.site.register(Cardapio)
admin.site.register(Prato)
admin.site.register(Aluno)
admin.site.register(Avaliacao)
admin.site.register(EstiloComida)
admin.site.register(Mapa)