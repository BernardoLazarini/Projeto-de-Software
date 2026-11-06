from django.urls import path
from . import views

urlpatterns = [
    path("", views.login, name="login"),
    path("sair/", views.sair, name="sair"),
    path("cadastro/", views.cadastrar, name="cadastro"),
    path("listausuarios/", views.listar_usuarios, name="listar_usuarios"),
    path("usuarios/<int:id>/editar/", views.editar, name="editar"),
    path("usuarios/<int:id>/excluir/", views.excluir, name="excluir"),
    path("restaurantes/", views.listar_restaurantes, name="restaurantes"),
    path("restaurantes/<int:id>/", views.detalhe_restaurante, name="detalhe_restaurante"),
]