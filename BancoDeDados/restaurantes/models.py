from django.db import models

# Create your models here.

from django.db import models


class EstiloComida(models.Model):
    nome = models.CharField(max_length=50)

    def __str__(self):
        return self.nome


class Mapa(models.Model):
    nome = models.CharField(max_length=100)

    def __str__(self):
        return self.nome


class Restaurante(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField()
    localizacao = models.CharField(max_length=200)
    mapa = models.ForeignKey(Mapa, on_delete=models.SET_NULL, null=True, blank=True)
    estilo = models.ForeignKey(EstiloComida, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return self.nome


class Cardapio(models.Model):
    restaurante = models.OneToOneField(Restaurante, on_delete=models.CASCADE)

    def __str__(self):
        return f"Cardápio de {self.restaurante}"


class Prato(models.Model):
    nome = models.CharField(max_length=100)
    preco = models.DecimalField(max_digits=7, decimal_places=2)
    cardapio = models.ForeignKey(Cardapio, on_delete=models.CASCADE)

    def __str__(self):
        return self.nome


class Aluno(models.Model):
    nome = models.CharField(max_length=100)
    username = models.CharField(max_length=50, unique=True)
    password = models.CharField(max_length=128)
    estilos_favoritos = models.ManyToManyField(EstiloComida, blank=True)

    def __str__(self):
        return self.nome


class Avaliacao(models.Model):
    estrela = models.PositiveSmallIntegerField()  # 1 a 5
    comentario = models.TextField(blank=True)
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE)
    restaurante = models.ForeignKey(Restaurante, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.estrela} estrelas - {self.restaurante}"