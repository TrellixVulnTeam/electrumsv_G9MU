# Pytest looks here for fixtures
import os
from os.path import dirname
from pathlib import Path
import shutil
import tempfile

import bitcoinx
import pytest
from electrumsv.transaction import Transaction, XPublicKey

from electrumsv.networks import Net, SVMainnet, SVTestnet
from electrumsv.simple_config import SimpleConfig
from electrumsv.util.misc import obj_size


@pytest.fixture(params=(SVMainnet, SVTestnet))
def coin(request):
    network = request.param
    Net.set_to(network)
    try:
        yield network.COIN
    finally:
        Net.set_to(SVMainnet)

def get_datacarrier_tx() -> Transaction:
    """datacarrier tx with one op_return output >6000 bytes and an xpubkey in the
    input - only for testing obj size calculation"""
    path = Path(dirname(os.path.realpath(__file__))).joinpath("data/transactions/data_carrier.txt")
    with open(path, "r") as f:
        rawtx = f.read()

    tx = Transaction.from_hex(rawtx)
    public_key_bytes = bitcoinx.PrivateKey(bytes.fromhex(
        'a2d9803c912ab380c1491d3bd1aaab34ca06742d7885a224ec8d386182d26ed2')
    ).public_key.to_bytes()
    tx.inputs[0].x_pubkeys[public_key_bytes] = XPublicKey.from_bytes(public_key_bytes)
    return tx

def get_small_tx() -> Transaction:
    path = Path(dirname(os.path.realpath(__file__))).joinpath("data/transactions/hello.txt")
    with open(path, "r") as f:
        rawtx = f.read()
    tx = Transaction.from_hex(rawtx)
    return tx

def get_tx_datacarrier_size() -> int:
    # the sizes vary depending on 32 vs 64 bit and versions of python (maybe linux vs windows too)
    return obj_size(get_datacarrier_tx())

def get_tx_small_size() -> int:
    # the sizes vary depending on 32 vs 64 bit and versions of python (maybe linux vs windows too)
    return obj_size(get_small_tx())

@pytest.fixture
def test_tx_datacarrier()-> Transaction:
    return get_datacarrier_tx()

@pytest.fixture
def test_tx_small()-> Transaction:
    return get_small_tx()

@pytest.fixture
def existing_config():
    electrum_sv_path = tempfile.mkdtemp()
    yield SimpleConfig({'electrum_sv_path': electrum_sv_path})
    shutil.rmtree(electrum_sv_path)


@pytest.fixture
def fresh_wallet_path():
    user_dir = tempfile.mkdtemp()
    yield os.path.join(user_dir, f"somewallet-{os.urandom(4).hex()}")
    shutil.rmtree(user_dir)
