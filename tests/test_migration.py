import brownie
import pytest
from brownie import Contract, Wei


def test_migration(
    chain,
    vaultA,
    vaultB,
    tokenA,
    tokenB,
    amountA,
    amountB,
    providerA,
    providerB,
    joint,
    gov,
    strategist,
    tokenA_whale,
    tokenB_whale,
    weth,
    ProviderStrategy,
    SushiJoint,
):

    tokenA.approve(vaultA, 2 ** 256 - 1, {"from": tokenA_whale})
    vaultA.deposit(amountA, {"from": tokenA_whale})

    tokenB.approve(vaultB, 2 ** 256 - 1, {"from": tokenB_whale})
    vaultB.deposit(amountB, {"from": tokenB_whale})

    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    assert joint.balanceOfStake() > 0
    tx = providerA.cloneProviderStrategy(
        providerA.vault(),
        providerA.strategist(),
        providerA.rewards(),
        providerA.keeper(),
    )
    new_a = ProviderStrategy.at(tx.events["Cloned"]["clone"])

    joint.liquidatePosition({"from": strategist})
    joint.returnLooseToProviders({"from": strategist})

    vaultA.migrateStrategy(providerA, new_a, {"from": vaultA.governance()})

    new_joint = SushiJoint.at(
        joint.cloneJoint(
            new_a,
            providerB,
            joint.router(),
            weth,
            joint.masterchef(),
            joint.reward(),
            joint.pid(),
            {"from": gov},
        ).return_value
    )

    new_a.setJoint(new_joint, {"from": vaultA.governance()})
    providerB.setJoint(new_joint, {"from": vaultB.governance()})

    new_a.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    # Wait plz
    chain.sleep(60 * 60 * 24 * 5)
    chain.mine(50)

    assert new_joint.pendingReward() > 0
    # If joint doesn't reinvest, and providers do not invest want, the want
    # will stay in the providers
    new_joint.setReinvest(False, {"from": strategist})
    new_a.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})
    new_a.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    assert new_a.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    chain.sleep(60 * 60 * 8)
    chain.mine(1)
    assert new_a.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0
    assert vaultA.strategies(new_a).dict()["totalGain"] == 0
    assert vaultB.strategies(providerB).dict()["totalGain"] == 0

    new_a.setTakeProfit(True, {"from": strategist})
    providerB.setTakeProfit(True, {"from": strategist})
    new_a.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})

    assert new_a.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    new_a.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    assert vaultA.strategies(new_a).dict()["totalGain"] > 0
    assert vaultB.strategies(providerB).dict()["totalGain"] > 0
