import pytest
from fastapi.testclient import TestClient

from supermarket_receipt_api.main import app  # adapte l'import si besoin

client = TestClient(app)


def post(payload):
    return client.post("/checkout", json=payload)


# ---------- Requêtes acceptées ----------

def test_panier_avec_promotion_3_pour_2():
    response = post({"items": [{"product_id": "toothbrush", "quantity": 3}]})

    assert response.status_code == 200
    assert response.json() == {
        "lines": [{
            "product_id": "toothbrush",
            "name": "Brosse à dents",
            "quantity": 3,
            "unit": "piece",
            "unit_price_cents": 99,
            "subtotal_cents": 297,
            "discount_cents": 99,
            "total_cents": 198,
        }],
        "subtotal_cents": 297,
        "discount_cents": 99,
        "total_cents": 198,
    }


def test_3_pour_2_ne_compte_que_les_groupes_complets():
    # 4 brosses : un seul groupe de 3, la 4e est au prix normal
    response = post({"items": [{"product_id": "toothbrush", "quantity": 4}]})

    line = response.json()["lines"][0]
    assert (line["subtotal_cents"], line["discount_cents"], line["total_cents"]) == (396, 99, 297)


def test_ticket_complet_tire_du_contrat():
    response = post({"items": [
        {"product_id": "toothbrush", "quantity": 3},
        {"product_id": "apples", "quantity": 500},
        {"product_id": "rice", "quantity": 2},
        {"product_id": "milk", "quantity": 2},
    ]})

    assert response.status_code == 200
    assert response.json() == {
        "lines": [
            {"product_id": "toothbrush", "name": "Brosse à dents", "quantity": 3,
             "unit": "piece", "unit_price_cents": 99,
             "subtotal_cents": 297, "discount_cents": 99, "total_cents": 198},
            {"product_id": "apples", "name": "Pommes", "quantity": 500,
             "unit": "gram", "unit_price_cents": 199,
             "subtotal_cents": 100, "discount_cents": 20, "total_cents": 80},
            {"product_id": "rice", "name": "Sac de riz", "quantity": 2,
             "unit": "piece", "unit_price_cents": 249,
             "subtotal_cents": 498, "discount_cents": 50, "total_cents": 448},
            {"product_id": "milk", "name": "Brique de lait", "quantity": 2,
             "unit": "piece", "unit_price_cents": 100,
             "subtotal_cents": 200, "discount_cents": 0, "total_cents": 200},
        ],
        "subtotal_cents": 1095,
        "discount_cents": 169,
        "total_cents": 926,
    }


def test_lignes_du_meme_produit_sont_regroupees_avant_calcul():
    # 2 + 1 = 3 brosses -> une seule ligne, promo appliquée
    response = post({"items": [
        {"product_id": "toothbrush", "quantity": 2},
        {"product_id": "toothbrush", "quantity": 1},
    ]})

    body = response.json()
    assert len(body["lines"]) == 1
    assert body["lines"][0]["quantity"] == 3
    assert body["discount_cents"] == 99


def test_panier_vide_est_accepte():
    response = post({"items": []})

    assert response.status_code == 200
    assert response.json() == {
        "lines": [], "subtotal_cents": 0, "discount_cents": 0, "total_cents": 0,
    }


# ---------- Requêtes refusées : 422 ----------

@pytest.mark.parametrize(
    "payload",
    [
        # champ manquant
        pytest.param({}, id="items_manquant"),
        pytest.param({"items": [{"quantity": 1}]}, id="product_id_manquant"),
        pytest.param({"items": [{"product_id": "milk"}]}, id="quantity_manquante"),
        # champ en trop
        pytest.param({"items": [], "extra": 1}, id="champ_en_trop_racine"),
        pytest.param(
            {"items": [{"product_id": "milk", "quantity": 1, "price": 1}]},
            id="champ_en_trop_dans_item",
        ),
        # champ mal typé
        pytest.param({"items": "milk"}, id="items_pas_une_liste"),
        pytest.param({"items": [{"product_id": 42, "quantity": 1}]}, id="product_id_entier"),
        pytest.param({"items": [{"product_id": "milk", "quantity": "2"}]}, id="quantity_chaine"),
        pytest.param({"items": [{"product_id": "milk", "quantity": 1.5}]}, id="quantity_fraction"),
        pytest.param({"items": [{"product_id": "milk", "quantity": True}]}, id="quantity_booleen"),
        # valeurs interdites
        pytest.param({"items": [{"product_id": "milk", "quantity": 0}]}, id="quantity_nulle"),
        pytest.param({"items": [{"product_id": "milk", "quantity": -1}]}, id="quantity_negative"),
    ],
)
def test_requete_invalide_donne_422(payload):
    response = post(payload)

    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.parametrize("product_id", ["bananas", "Milk", "MILK", ""])
def test_produit_inconnu_donne_422_avec_message_metier(product_id):
    # sensible à la casse : "Milk" n'est pas "milk"
    response = post({"items": [{"product_id": product_id, "quantity": 1}]})

    assert response.status_code == 422
    # erreur métier -> message texte, pas la liste d'erreurs de schéma FastAPI
    assert isinstance(response.json()["detail"], str)