from django.urls import path
from . import views

urlpatterns = [
    path("", views.login, name="login"),
    path("cadastro/", views.cadastrar, name="cadastro"),
    path("usuarios/", views.listar_usuarios, name="listar_usuarios"),
        path("usuarios/<int:id>/editar/", views.editar, name="editar"),
    path("usuarios/<int:id>/excluir/", views.excluir, name="excluir"),
]

