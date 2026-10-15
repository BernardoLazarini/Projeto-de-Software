from django.contrib import admin

# Register your models here.

from django.contrib import admin
from .models import EstiloComida, Mapa, Restaurante, Cardapio, Prato, Aluno, Avaliacao

admin.site.register([EstiloComida, Mapa, Restaurante, Cardapio, Prato, Aluno, Avaliacao])

