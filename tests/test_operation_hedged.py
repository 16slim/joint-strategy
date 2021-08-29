import brownie
import pytest
from brownie import Contract, Wei
from operator import xor


def test_operation_hedged(
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
    strategist,
    tokenA_whale,
    tokenB_whale,
    LPHedgingLibrary,
):

    tokenA.approve(vaultA, 2 ** 256 - 1, {"from": tokenA_whale})
    vaultA.deposit(amountA, {"from": tokenA_whale})

    tokenB.approve(vaultB, 2 ** 256 - 1, {"from": tokenB_whale})
    vaultB.deposit(amountB, {"from": tokenB_whale})

    ppsA_start = vaultA.pricePerShare()
    ppsB_start = vaultB.pricePerShare()

    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    # disabling this bc im paying for options and leaving uninvested funds (< 1%)
    # assert xor(
    #     providerA.balanceOfWant() > 0, providerB.balanceOfWant() > 0
    # )  # exactly one should have some remainder
    assert joint.balanceOfA() == 0
    assert joint.balanceOfB() == 0
    assert joint.balanceOfStake() > 0

    investedA = (
        vaultA.strategies(providerA).dict()["totalDebt"] - providerA.balanceOfWant()
    )
    investedB = (
        vaultB.strategies(providerB).dict()["totalDebt"] - providerB.balanceOfWant()
    )

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # Wait plz
    chain.sleep(3600 * 24 * 1)
    chain.mine(int(3600 / 13) * 24 * 1)

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # If there is any profit it should go to the providers
    assert joint.pendingReward() > 0
    # If joint doesn't reinvest, and providers do not invest want, the want
    # will stay in the providers
    providerA.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})
    providerA.setTakeProfit(True, {"from": strategist})
    providerB.setTakeProfit(True, {"from": strategist})
    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    assert providerA.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    gainA = vaultA.strategies(providerA).dict()["totalGain"]
    gainB = vaultB.strategies(providerB).dict()["totalGain"]

    assert gainA > 0
    assert gainB > 0

    returnA = gainA / investedA
    returnB = gainB / investedB

    print(
        f"Return: {returnA*100:.5f}% {tokenA.symbol()} {returnB*100:.5f}% {tokenB.symbol()}"
    )

    assert pytest.approx(returnA, rel=50e-3) == returnB

    # Harvest should be a no-op
    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    chain.sleep(60 * 60 * 8)
    chain.mine(1)
    assert providerA.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    chain.sleep(60 * 60 * 8)
    chain.mine(1)
    assert vaultA.strategies(providerA).dict()["totalGain"] > 0
    assert vaultB.strategies(providerB).dict()["totalGain"] > 0

    assert vaultA.pricePerShare() > ppsA_start
    assert vaultB.pricePerShare() > ppsB_start


def test_operation_swap_a4b_hedged_light(
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
    router,
    strategist,
    tokenA_whale,
    tokenB_whale,
    mock_chainlink,
):
    oracle = Contract(
        Contract("0xb9ed94c6d594b2517c4296e24A8c517FF133fb6d").priceProvider()
    )
    pair = Contract(joint.pair())
    (reserve0, reserve1, a) = pair.getReserves()
    mock_chainlink.setPrice(reserve0 / reserve1 * 1e12 * 10 ** 8, {"from": strategist})
    print(f"Price according to Pair {pair.address} is {reserve0/reserve1*1e12}")
    print(f"Price according to Pair {pair.address} is {oracle.latestAnswer()/1e8}")

    tokenA.approve(vaultA, 2 ** 256 - 1, {"from": tokenA_whale})
    vaultA.deposit(amountA, {"from": tokenA_whale})

    tokenB.approve(vaultB, 2 ** 256 - 1, {"from": tokenB_whale})
    vaultB.deposit(amountB, {"from": tokenB_whale})

    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    # disabling this bc im paying for options and leaving uninvested funds (< 1%)
    # assert xor(
    #     providerA.balanceOfWant() > 0, providerB.balanceOfWant() > 0
    # )  # exactly one should have some remainder
    assert joint.balanceOfA() == 0
    assert joint.balanceOfB() == 0
    assert joint.balanceOfStake() > 0

    investedA = (
        vaultA.strategies(providerA).dict()["totalDebt"] - providerA.balanceOfWant()
    )
    investedB = (
        vaultB.strategies(providerB).dict()["totalDebt"] - providerB.balanceOfWant()
    )
    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    callID = joint.activeCallID()
    putID = joint.activePutID()
    callProvider = Contract("0xb9ed94c6d594b2517c4296e24A8c517FF133fb6d")
    putProvider = Contract("0x790e96E7452c3c2200bbCAA58a468256d482DD8b")
    callInfo = callProvider.options(callID)
    putInfo = putProvider.options(putID)
    assert (joint.activeCallID() != 0) & (joint.activePutID() != 0)
    print(f"Bought two options:")
    print(f"CALL #{callID}")
    print(f"\tStrike {callInfo[1]/1e8}")
    print(f"\tAmount {callInfo[2]/1e18}")
    print(f"\tTTM {(callInfo[4]-chain.time())/3600}h")
    costCall = (callInfo[5]+callInfo[6])/0.8
    investedA -= costCall
    print(f"\tCost {(callInfo[5]+callInfo[6])/0.8/1e18} {tokenA.symbol()}")
    print(f"PUT #{putID}")
    print(f"\tStrike {putInfo[1]/1e8}")
    print(f"\tAmount {putInfo[2]/1e18}")
    print(f"\tTTM {(putInfo[4]-chain.time())/3600}h")
    costPut = (putInfo[5]+putInfo[6])/0.8
    investedB -= costPut
    print(f"\tCost {costPut/1e6} {tokenB.symbol()}")

    tokenA.approve(router, 2 ** 256 - 1, {"from": tokenA_whale})
    dump_amountA = 0.001 * tokenA.balanceOf(tokenA_whale)
    print(f"Dumping some tokenA. Selling {dump_amountA / 1e18} {tokenA.symbol()}")
    router.swapExactTokensForTokens(
        dump_amountA,
        0,
        [tokenA, tokenB],
        tokenA_whale,
        2 ** 256 - 1,
        {"from": tokenA_whale},
    )
    (reserve0, reserve1, a) = pair.getReserves()
    mock_chainlink.setPrice(reserve0 / reserve1 * 1e12 * 10 ** 8, {"from": strategist})
    print(f"Price according to Pair {pair.address} is {oracle.latestAnswer()/1e8}")
    (callPayout, putPayout) = joint.getOptionsProfit()
    print(f"Payout from CALL option: {callPayout/1e18} {tokenA.symbol()}")
    print(f"Payout from PUT option: {putPayout/1e6} {tokenB.symbol()}")
    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # Wait plz
    chain.sleep(3600 * 24 * 1 - 15 * 60)
    chain.mine(int(3600 / 13) * 24 * 1 - int(60 * 15 / 13))

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # If there is any profit it should go to the providers
    assert joint.pendingReward() > 0
    # If joint doesn't reinvest, and providers do not invest want, the want
    # will stay in the providers
    providerA.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})
    providerA.setTakeProfit(True, {"from": strategist})
    providerB.setTakeProfit(True, {"from": strategist})
    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    callInfo = callProvider.options(callID)
    putInfo = putProvider.options(putID)

    assert ((callInfo[0] == 2) & (callPayout > 0)) | ((callPayout == 0) & (callInfo[0] == 1))
    assert ((putInfo[0] == 2) & (putPayout > 0)) | ((putPayout == 0) & (putInfo[0] == 1))

    assert providerA.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    gainA = vaultA.strategies(providerA).dict()["totalGain"]
    gainB = vaultB.strategies(providerB).dict()["totalGain"]

    lossA = vaultA.strategies(providerA).dict()["totalLoss"]
    lossB = vaultB.strategies(providerB).dict()["totalLoss"]

    assert lossA == 0
    assert lossB == 0
    assert gainA > 0
    assert gainB > 0

    returnA = gainA / investedA
    returnB = gainB / investedB

    print(
        f"Return: {returnA*100:.5f}% {tokenA.symbol()} {returnB*100:.5f}% {tokenB.symbol()}"
    )

    assert pytest.approx(returnA, rel=50e-3) == returnB


def test_operation_swap_a4b_hedged_heavy(
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
    router,
    strategist,
    tokenA_whale,
    tokenB_whale,
):
    tokenA.approve(vaultA, 2 ** 256 - 1, {"from": tokenA_whale})
    vaultA.deposit(amountA, {"from": tokenA_whale})

    tokenB.approve(vaultB, 2 ** 256 - 1, {"from": tokenB_whale})
    vaultB.deposit(amountB, {"from": tokenB_whale})

    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    # disabling this bc im paying for options and leaving uninvested funds (< 1%)
    # assert xor(
    #     providerA.balanceOfWant() > 0, providerB.balanceOfWant() > 0
    # )  # exactly one should have some remainder
    assert joint.balanceOfA() == 0
    assert joint.balanceOfB() == 0
    assert joint.balanceOfStake() > 0

    investedA = (
        vaultA.strategies(providerA).dict()["totalDebt"] - providerA.balanceOfWant()
    )
    investedB = (
        vaultB.strategies(providerB).dict()["totalDebt"] - providerB.balanceOfWant()
    )
    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    tokenA.approve(router, 2 ** 256 - 1, {"from": tokenA_whale})
    print(
        f"Dumping tokenA really bad. Selling {tokenA.balanceOf(tokenA_whale) / 1e18} {tokenA.symbol()}"
    )
    router.swapExactTokensForTokens(
        tokenA.balanceOf(tokenA_whale),
        0,
        [tokenA, tokenB],
        tokenA_whale,
        2 ** 256 - 1,
        {"from": tokenA_whale},
    )

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # Wait plz
    chain.sleep(3600 * 24 * 1)
    chain.mine(int(3600 / 13) * 24 * 1)

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # If there is any profit it should go to the providers
    assert joint.pendingReward() > 0
    # If joint doesn't reinvest, and providers do not invest want, the want
    # will stay in the providers
    providerA.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})
    providerA.setTakeProfit(True, {"from": strategist})
    providerB.setTakeProfit(True, {"from": strategist})
    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    assert providerA.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    lossA = vaultA.strategies(providerA).dict()["totalLoss"]
    lossB = vaultB.strategies(providerB).dict()["totalLoss"]

    assert lossA > 0
    assert lossB > 0

    returnA = -lossA / investedA
    returnB = -lossB / investedB

    print(
        f"Return: {returnA*100:.5f}% {tokenA.symbol()} {returnB*100:.5f}% {tokenB.symbol()}"
    )

    assert pytest.approx(returnA, rel=50e-3) == returnB


def test_operation_swap_b4a_hedged_light(
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
    router,
    strategist,
    tokenA_whale,
    tokenB_whale,
):

    tokenA.approve(vaultA, 2 ** 256 - 1, {"from": tokenA_whale})
    vaultA.deposit(amountA, {"from": tokenA_whale})

    tokenB.approve(vaultB, 2 ** 256 - 1, {"from": tokenB_whale})
    vaultB.deposit(amountB, {"from": tokenB_whale})

    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    # disabling this bc im paying for options and leaving uninvested funds (< 1%)
    # assert xor(
    #     providerA.balanceOfWant() > 0, providerB.balanceOfWant() > 0
    # )  # exactly one should have some remainder
    assert joint.balanceOfA() == 0
    assert joint.balanceOfB() == 0
    assert joint.balanceOfStake() > 0

    investedA = (
        vaultA.strategies(providerA).dict()["totalDebt"] - providerA.balanceOfWant()
    )
    investedB = (
        vaultB.strategies(providerB).dict()["totalDebt"] - providerB.balanceOfWant()
    )
    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    tokenB.approve(router, 2 ** 256 - 1, {"from": tokenB_whale})
    print(
        f"Dumping tokenB really bad. Selling {tokenB.balanceOf(tokenB_whale) / 1e6} {tokenB.symbol()}"
    )

    router.swapExactTokensForTokens(
        tokenB.balanceOf(tokenB_whale),
        0,
        [tokenB, tokenA],
        tokenB_whale,
        2 ** 256 - 1,
        {"from": tokenB_whale},
    )

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # Wait plz
    chain.sleep(3600 * 1)
    chain.mine(int(3600 / 13))

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # If there is any profit it should go to the providers
    assert joint.pendingReward() > 0
    # If joint doesn't reinvest, and providers do not invest want, the want
    # will stay in the providers
    providerA.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})
    providerA.setTakeProfit(True, {"from": strategist})
    providerB.setTakeProfit(True, {"from": strategist})
    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    assert providerA.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    lossA = vaultA.strategies(providerA).dict()["totalLoss"]
    lossB = vaultB.strategies(providerB).dict()["totalLoss"]

    assert lossA > 0
    assert lossB > 0

    returnA = -lossA / investedA
    returnB = -lossB / investedB

    print(
        f"Return: {returnA*100:.5f}% {tokenA.symbol()} {returnB*100:.5f}% {tokenB.symbol()}"
    )

    assert pytest.approx(returnA, rel=50e-3) == returnB


def test_operation_swap_b4a_hedged_heavy(
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
    router,
    strategist,
    tokenA_whale,
    tokenB_whale,
):

    tokenA.approve(vaultA, 2 ** 256 - 1, {"from": tokenA_whale})
    vaultA.deposit(amountA, {"from": tokenA_whale})

    tokenB.approve(vaultB, 2 ** 256 - 1, {"from": tokenB_whale})
    vaultB.deposit(amountB, {"from": tokenB_whale})

    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})
    # disabling this bc im paying for options and leaving uninvested funds (< 1%)
    # assert xor(
    #     providerA.balanceOfWant() > 0, providerB.balanceOfWant() > 0
    # )  # exactly one should have some remainder
    assert joint.balanceOfA() == 0
    assert joint.balanceOfB() == 0
    assert joint.balanceOfStake() > 0

    investedA = (
        vaultA.strategies(providerA).dict()["totalDebt"] - providerA.balanceOfWant()
    )
    investedB = (
        vaultB.strategies(providerB).dict()["totalDebt"] - providerB.balanceOfWant()
    )
    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    tokenB.approve(router, 2 ** 256 - 1, {"from": tokenB_whale})
    print(
        f"Dumping tokenB really bad. Selling {tokenB.balanceOf(tokenB_whale) / 1e6} {tokenB.symbol()}"
    )

    router.swapExactTokensForTokens(
        tokenB.balanceOf(tokenB_whale),
        0,
        [tokenB, tokenA],
        tokenB_whale,
        2 ** 256 - 1,
        {"from": tokenB_whale},
    )

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # Wait plz
    chain.sleep(3600 * 1)
    chain.mine(int(3600 / 13))

    print(
        f"Joint estimated assets: {joint.estimatedTotalAssetsInToken(tokenA) / 1e18} {tokenA.symbol()} and {joint.estimatedTotalAssetsInToken(tokenB) / 1e6} {tokenB.symbol()}"
    )

    # If there is any profit it should go to the providers
    assert joint.pendingReward() > 0
    # If joint doesn't reinvest, and providers do not invest want, the want
    # will stay in the providers
    providerA.setInvestWant(False, {"from": strategist})
    providerB.setInvestWant(False, {"from": strategist})
    providerA.setTakeProfit(True, {"from": strategist})
    providerB.setTakeProfit(True, {"from": strategist})
    providerA.harvest({"from": strategist})
    providerB.harvest({"from": strategist})

    assert providerA.balanceOfWant() > 0
    assert providerB.balanceOfWant() > 0

    lossA = vaultA.strategies(providerA).dict()["totalLoss"]
    lossB = vaultB.strategies(providerB).dict()["totalLoss"]

    assert lossA > 0
    assert lossB > 0

    returnA = -lossA / investedA
    returnB = -lossB / investedB

    print(
        f"Return: {returnA*100:.5f}% {tokenA.symbol()} {returnB*100:.5f}% {tokenB.symbol()}"
    )

    assert pytest.approx(returnA, rel=50e-3) == returnB
