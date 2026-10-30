"""
URL configuration for noPonto project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

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