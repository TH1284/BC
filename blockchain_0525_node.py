import hashlib
import time
import csv
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import json
import re
from urllib.parse import parse_qs
from urllib.parse import urlparse
import threading
import cgi
import uuid
from tempfile import NamedTemporaryFile
import shutil
import requests  # for sending new block to other nodes
import pandas as pd
from sqlalchemy import create_engine

IP = '127.0.0.1'
PORT_NUMBER = 8099
# engine = create_engine('oracle+cx_oracle://HYUN:Hyun@{}:1522/xe'.format(IP))
engine = create_engine('oracle+cx_oracle://KOPO:kopo@192.168.110.112:1521/orcl')
g_txFileName = "txData.csv"
g_bcFileName = "blockchain.csv"
g_nodelstFileName = "nodelst.csv"
g_txTableName = 'txdata'
g_bcTableName = 'blockchain'
g_nodelstTableName = 'node'
g_receiveNewBlock = "/node/receiveNewBlock"
g_difficulty = 2
g_maximumTry = 100
g_nodeList = {'trustedServerAddress': '8099'}  # trusted server list, should be checked manually


class Block:

    def __init__(self, index, previousHash, timestamp, data, currentHash, proof, fee, signature):
        self.index = index
        self.previousHash = previousHash
        self.timestamp = timestamp
        self.data = data
        self.currentHash = currentHash
        self.proof = proof
        self.fee = fee
        self.signature = signature

    def toJSON(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


class txData:

    def __init__(self, commitYN, sender, amount, receiver, uuid, fee, message, txTime):
        self.commitYN = commitYN
        self.sender = sender
        self.amount = amount
        self.receiver = receiver
        self.uuid = uuid
        self.fee = fee
        self.message = message
        self.txTime = txTime


def selectTable(tableName):
    try:
        table = pd.read_sql_query('select * from {}'.format(tableName), engine)
    except:
        table = pd.DataFrame
    return table


def insertIntoBlockchain(Block):
    try:
        pd.read_sql_query("insert into blockchain values ({}, '{}', '{}', '{}', '{}', {}, {}, '{}')".format(Block.index,
                                                                                                            Block.previousHash,
                                                                                                            Block.timestamp,
                                                                                                            Block.data,
                                                                                                            Block.currentHash,
                                                                                                            Block.proof,
                                                                                                            Block.fee,
                                                                                                            Block.signature),
                          engine)
    except:
        pass


def insertIntoTxdata(txData):
    try:
        pd.read_sql_query("insert into txdata values ({}, '{}', {}, '{}', '{}', {}, '{}', '{}')".format(txData.commitYN,
                                                                                                        txData.sender,
                                                                                                        txData.amount,
                                                                                                        txData.receiver,
                                                                                                        txData.uuid,
                                                                                                        txData.fee,
                                                                                                        txData.message,
                                                                                                        txData.txTime),
                          engine)
    except:
        pass


def insertIntoNodelist(ip, port):
    try:
        pd.read_sql_query("insert into node values ('{}', '{}')".format(ip, port), engine)
    except:
        pass


def generateGenesisBlock():
    print("generateGenesisBlock is called")
    timestamp = time.time()
    print("time.time() => %f \n" % timestamp)
    tempHash = calculateHash(0, '0', timestamp, "Genesis Block", 0, 0, 'Genesis')
    print(tempHash)
    block = Block(0, '0', timestamp, "Genesis Block", tempHash, 0, 0, "Genesis")
    insertIntoBlockchain(block)
    return block


def calculateHash(index, previousHash, timestamp, data, proof, fee, signature):
    value = str(index) + str(previousHash) + str(timestamp) + str(data) + str(proof) + str(fee) + str(signature)
    sha = hashlib.sha256(value.encode('utf-8'))
    return str(sha.hexdigest())


def messageHash(message):
    sha = hashlib.sha256(message.encode('utf-8'))
    return str(sha.hexdigest())


def calculateHashForBlock(block):
    return calculateHash(block.index, block.previousHash, block.timestamp, block.data, block.proof, block.fee,
                         block.signature)


def getLatestBlock(blockchain):
    return blockchain[len(blockchain) - 1]


def generateNextBlock(blockchain, blockData, timestamp, proof, fee, signature):
    previousBlock = getLatestBlock(blockchain)
    nextIndex = int(previousBlock.index) + 1
    nextTimestamp = timestamp
    nextHash = calculateHash(nextIndex, previousBlock.currentHash, nextTimestamp, blockData, proof, fee, signature)
    # index, previousHash, timestamp, data, currentHash, proof
    return Block(nextIndex, previousBlock.currentHash, nextTimestamp, blockData, nextHash, proof, fee, signature)


def writeBlockchain(blockchain):
    # [STARAT] check current db(csv) if broadcasted block data has already been updated
    lastBlock = None
    try:
        blockReader = selectTable(g_bcTableName)
        last_line_number = len(blockReader)
        lastBlock = blockReader.iloc[last_line_number - 1:last_line_number, :]
        if int(lastBlock.index) + 1 != int(blockchain.no[-1]):
            print("index sequence mismatch")
            if int(lastBlock.index) == int(blockchain.no[-1]):
                print("db has already been updated")
            return
    except:
        print("file open error in check current db \n or maybe there's some other reason")
        pass
        # return
    # [END] check current db(csv)
    newBlock = Block(blockchain.no[-1], blockchain.previousHash[-1], blockchain.timestamp[-1], blockchain.data[-1],
                     blockchain.currentHash[-1], blockchain.proof[-1], blockchain.fee[-1], blockchain.signature[-1])
    insertIntoBlockchain(newBlock)

    # update txData cause it has been mined.
    for block in blockchain:
        updateTx(block)

    print('Blockchain written to blockchain.csv.')
    print('Broadcasting new block to other nodes')
    broadcastNewBlock(blockchain)


def readBlockchain(g_bcTableName):
    print("readBlockchain")
    try:
        importedBlockchain = selectTable(g_bcTableName)
        if len(importedBlockchain) == 0:
            generateGenesisBlock()
            importedBlockchain = selectTable(g_bcTableName)
        return importedBlockchain
    except:
        return None


def updateTx(blockData):
    phrase = re.compile(
        r"\w+[-]\w+[-]\w+[-]\w+[-]\w+")  # [6b3b3c1e-858d-4e3b-b012-8faac98b49a8]UserID hwang sent 333 bitTokens to UserID kim.
    matchList = phrase.findall(blockData.data)

    if len(matchList) == 0:
        print("No Match Found! " + str(blockData.data) + "block idx: " + str(blockData.index))
        return

        reader = selectTable(g_txTableName)
        for i in range(len(reader)):
            if reader.uuid[i] in matchList:
                print('updating row : ', reader.uuid[i])
                try:
                    pd.read_sql_query("update txdata set commityn = 1 WHERE uuid = '{}'".format(reader.uuid[i]))
                except:
                    pass
    print('txData updated')


def writeTx(txRawData):
    print(g_txFileName)
    txDataList = []
    for txDatum in txRawData:
        txList = [txDatum.commitYN, txDatum.sender, txDatum.amount, txDatum.receiver, txDatum.uuid, txDatum.fee,
                  txDatum.message, txDatum.txTime]
        txDataList.append(txList)

    tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
    try:
        with open(g_txFileName, 'r', newline='') as csvfile, tempfile:
            reader = csv.reader(csvfile)
            writer = csv.writer(tempfile)
            for row in reader:
                if row:
                    writer.writerow(row)
            # adding new tx
            writer.writerows(txDataList)
        shutil.move(tempfile.name, g_txFileName)
        csvfile.close()
        tempfile.close()
    except:
        # this is 1st time of creating txFile
        try:
            with open(g_txFileName, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerows(txDataList)
        except:
            return 0
    return 1
    print('txData written to txData.csv.')


def readTx(g_txTableName):
    print("readTx")
    try:
        importedTx = selectTable(g_txTableName)
        return importedTx
    except:
        return None


def getTxData():
    strTxData = ''
    importedTx = readTx(g_txTableName)
    if len(importedTx) != 0:
        for i in range(len(importedTx)):
            Dict = {'no': str(importedTx.no[i]), 'previoushash': importedTx.previoushash[i],
                    'timestamp': importedTx.timestamp[i], 'data': importedTx.data[i],
                    'currenthash': importedTx.currenthash[i], 'proof': str(importedTx.proof[i]),
                    'fee': str(importedTx.fee[i]), 'signature': importedTx.signature[i]}
            print(Dict)
            transaction = "[" + i.uuid + "]" "UserID " + i.sender + " sent " + i.amount + " bitTokens to UserID " + i.receiver + " fee " + i.fee + "message: " + i.message + ", time : " + i.txTime  #
            print(transaction)
            strTxData += transaction

    return strTxData


def getfeeData():
    temp = 0
    importedTx = readTx(g_txFileName)
    if len(importedTx) > 0:
        for i in importedTx:
            temp = int(temp) + int(i.fee)
    return temp


def mineNewBlock(difficulty=g_difficulty, blockchainPath=g_bcTableName):
    blockchain = readBlockchain(blockchainPath)

    strTxData = getTxData()
    if strTxData == '':
        print('No TxData Found. Mining aborted')
        return

    timestamp = time.time()
    proof = 0
    newBlockFound = False

    print('Mining a block...')

    while not newBlockFound:
        newBlockAttempt = generateNextBlock(blockchain, strTxData, timestamp, proof, fee, signature)
        if newBlockAttempt.currentHash[0:difficulty] == '0' * difficulty:
            stopTime = time.time()
            timer = stopTime - timestamp
            print('New block found with proof', proof, 'in', round(timer, 2), 'seconds.')
            newBlockFound = True
        else:
            proof += 1

    blockchain.loc[len(blockchain)] = [newBlockAttempt.index, newBlockAttempt.previousHash, newBlockAttempt.timestamp,
                                       newBlockAttempt.data, newBlockAttempt.currentHash, newBlockAttempt.proof,
                                       newBlockAttempt.fee, newBlockAttempt.signature]
    writeBlockchain(blockchain)


def mine():
    mineNewBlock()


def isSameBlock(block1, block2):
    if str(block1.index) != str(block2.index):
        return False
    elif str(block1.previousHash) != str(block2.previousHash):
        return False
    elif str(block1.timestamp) != str(block2.timestamp):
        return False
    elif str(block1.data) != str(block2.data):
        return False
    elif str(block1.currentHash) != str(block2.currentHash):
        return False
    elif str(block1.proof) != str(block2.proof):
        return False
    elif str(block1.fee) != str(block2.fee):
        return False
    elif str(block1.signature) != str(block2.signature):
        return False
    return True


def isValidNewBlock(newBlock, previousBlock):
    if int(previousBlock.index) + 1 != int(newBlock.index):
        print('Indices Do Not Match Up')
        return False
    elif previousBlock.currentHash != newBlock.previousHash:
        print("Previous hash does not match")
        return False
    elif calculateHashForBlock(newBlock) != newBlock.currentHash:
        print("Hash is invalid")
        return False
    elif newBlock.currentHash[0:g_difficulty] != '0' * g_difficulty:
        print("Hash difficulty is invalid")
        return False
    return True


def newtx(txToMining):
    newtxData = []
    # transform given data to txData object
    for line in txToMining:
        tx = txData(0, line['sender'], line['amount'], line['receiver'], uuid.uuid4(), line['fee'], line['message'],
                    txTime)
        newtxData.append(tx)

    # limitation check : max 5 tx
    if len(newtxData) > 5:
        print('number of requested tx exceeds limitation')
        return -1

    if writeTx(newtxData) == 0:
        print("file write error on txData")
        return -2
    return 1


def isValidChain(bcToValidate):
    genesisBlock = []
    bcToValidateForBlock = []

    # Read GenesisBlock
    try:
        with open(g_bcFileName, 'r', newline='') as file:
            blockReader = csv.reader(file)
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5], line[6], line[7])
                genesisBlock.append(block)
    #                break
    except:
        print("file open error in isValidChain")
        return False

    # transform given data to Block object
    for line in bcToValidate:
        # print(type(line))
        # index, previousHash, timestamp, data, currentHash, proof
        block = Block(line['index'], line['previousHash'], line['timestamp'], line['data'], line['currentHash'],
                      line['proof'], line['fee'], line['signature'])
        bcToValidateForBlock.append(block)

    # if it fails to read block data  from db(csv)
    if not genesisBlock:
        print("fail to read genesisBlock")
        return False

    # compare the given data with genesisBlock
    if not isSameBlock(bcToValidateForBlock[0], genesisBlock[0]):
        print('Genesis Block Incorrect')
        return False

    # tempBlocks = [bcToValidateForBlock[0]]
    # for i in range(1, len(bcToValidateForBlock)):
    #    if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
    #        tempBlocks.append(bcToValidateForBlock[i])
    #    else:
    #        return False

    for i in range(0, len(bcToValidateForBlock)):
        if isSameBlock(genesisBlock[i], bcToValidateForBlock[i]) == False:
            return False

    return True


def addNode(queryStr):
    inputNodeIp = queryStr[0]
    inputNodePort = queryStr[1]

    importedNodeList = selectTable(g_nodelstTableName)

    try:
        if (len(importedNodeList) > 0):
            for i in range(len(importedNodeList)):
                if inputNodeIp == importedNodeList.ip[i] and inputNodePort == importedNodeList.port[i]:
                    print("requested node is already exists")
                    return -1

    except:
        return 0

    insertIntoNodelist(inputNodeIp, inputNodePort)
    print('new node written to DB')
    return 1


def readNodes(g_nodelstTableName):
    print("read Nodes")

    try:
        importedNodeList = selectTable(g_nodelstTableName)
        return importedNodeList
    except:
        return None


def broadcastNewBlock(blockchain):
    # newBlock  = getLatestBlock(blockchain) # get the latest block
    importedNodes = readNodes(g_nodelstFileName)  # get server node ip and port
    reqHeader = {'Content-Type': 'application/json; charset=utf-8'}
    reqBody = []
    for i in blockchain:
        reqBody.append(i.__dict__)

    if len(importedNodes) > 0:
        for node in importedNodes:
            try:
                URL = "http://" + node[0] + ":" + node[1] + g_receiveNewBlock  # http://ip:port/node/receiveNewBlock
                res = requests.post(URL, headers=reqHeader, data=json.dumps(reqBody))
                if res.status_code == 200:
                    print(URL + " sent ok.")
                    print("Response Message " + res.text)
                else:
                    print(URL + " responding error " + res.status_code)
            except:
                print(URL + " is not responding.")
                # write responding results
                tempfile = NamedTemporaryFile(mode='w', newline='', delete=False)
                try:
                    with open(g_nodelstFileName, 'r', newline='') as csvfile, tempfile:
                        reader = csv.reader(csvfile)
                        writer = csv.writer(tempfile)
                        for row in reader:
                            if row:
                                if row[0] == node[0] and row[1] == node[1]:
                                    print("connection failed " + row[0] + ":" + row[1] + ", number of fail " + row[2])
                                    tmp = row[2]
                                    # too much fail, delete node
                                    if int(tmp) > g_maximumTry:
                                        print(row[0] + ":" + row[
                                            1] + " deleted from node list because of exceeding the request limit")
                                    else:
                                        row[2] = int(tmp) + 1
                                        writer.writerow(row)
                                else:
                                    writer.writerow(row)
                    shutil.move(tempfile.name, g_nodelstFileName)
                    csvfile.close()
                    tempfile.close()
                except:
                    print("caught exception while updating node list")


def compareMerge(bcDict):
    heldBlock = []
    bcToValidateForBlock = []

    # Read GenesisBlock
    try:
        with open(g_bcFileName, 'r', newline='') as file:
            blockReader = csv.reader(file)
            # last_line_number = row_count(g_bcFileName)
            for line in blockReader:
                block = Block(line[0], line[1], line[2], line[3], line[4], line[5], line[6], line[7])
                heldBlock.append(block)
                # if blockReader.line_num == 1:
                #    block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                #    heldBlock.append(block)
                # elif blockReader.line_num == last_line_number:
                #    block = Block(line[0], line[1], line[2], line[3], line[4], line[5])
                #    heldBlock.append(block)

    except:
        print("file open error in compareMerge or No database exists")
        print("call initSvr if this server has just installed")
        return -1

    # if it fails to read block data  from db(csv)
    if len(heldBlock) == 0:
        print("fail to read")
        return -2

    # transform given data to Block object
    for line in bcDict:
        # print(type(line))
        # index, previousHash, timestamp, data, currentHash, proof
        block = Block(line['index'], line['previousHash'], line['timestamp'], line['data'], line['currentHash'],
                      line['proof'], line['signature'])
        bcToValidateForBlock.append(block)

    # compare the given data with genesisBlock
    if not isSameBlock(bcToValidateForBlock[0], heldBlock[0]):
        print('Genesis Block Incorrect')
        return -1

    # check if broadcasted new block,1 ahead than > last held block

    if isValidNewBlock(bcToValidateForBlock[-1], heldBlock[-1]) == False:

        # latest block == broadcasted last block
        if isSameBlock(heldBlock[-1], bcToValidateForBlock[-1]) == True:
            print('latest block == broadcasted last block, already updated')
            return 2
        # select longest chain
        elif len(bcToValidateForBlock) > len(heldBlock):
            # validation
            if isSameBlock(heldBlock[0], bcToValidateForBlock[0]) == False:
                print("Block Information Incorrect #1")
                return -1
            tempBlocks = [bcToValidateForBlock[0]]
            for i in range(1, len(bcToValidateForBlock)):
                if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
                    tempBlocks.append(bcToValidateForBlock[i])
                else:
                    return -1
            # [START] save it to csv
            blockchainList = []
            blockList = [block.index, block.previousHash, str(block.timestamp), block.data, block.currentHash,
                         block.proof, block.fee, block.signature]
            blockchainList.append(blockList)
            with open(g_bcFileName, "w", newline='') as file:
                writer = csv.writer(file)
                writer.writerows(blockchainList)
            # [END] save it to csv
            return 1
        elif len(bcToValidateForBlock) < len(heldBlock):
            # validation
            # for i in range(0,len(bcToValidateForBlock)):
            #    if isSameBlock(heldBlock[i], bcToValidateForBlock[i]) == False:
            #        print("Block Information Incorrect #1")
            #        return -1
            tempBlocks = [bcToValidateForBlock[0]]
            for i in range(1, len(bcToValidateForBlock)):
                if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
                    tempBlocks.append(bcToValidateForBlock[i])
                else:
                    return -1
            print("We have a longer chain")
            return 3
        else:
            print("Block Information Incorrect #2")
            return -1
    else:  # very normal case (ex> we have index 100 and receive index 101 ...)
        tempBlocks = [bcToValidateForBlock[0]]
        for i in range(1, len(bcToValidateForBlock)):
            if isValidNewBlock(bcToValidateForBlock[i], tempBlocks[i - 1]):
                tempBlocks.append(bcToValidateForBlock[i])
            else:
                print("Block Information Incorrect #2 " + tempBlocks.__dict__)
                return -1

        print("new block good")

        # validation
        for i in range(0, len(heldBlock)):
            if isSameBlock(heldBlock[i], bcToValidateForBlock[i]) == False:
                print("Block Information Incorrect #1")
                return -1
        # [START] save it to csv
        blockchainList = []
        for block in bcToValidateForBlock:
            blockList = [block.index, block.previousHash, str(block.timestamp), block.data, block.currentHash,
                         block.proof, block.fee, block.signature]
            blockchainList.append(blockList)
        with open(g_bcFileName, "w", newline='') as file:
            writer = csv.writer(file)
            writer.writerows(blockchainList)
        # [END] save it to csv
        return 1


def initSvr():
    print("init Server")
    # 1. check if we have a node list file
    last_line_number = len(selectTable(g_nodelstTableName))
    # if we don't have, let's request node list
    if last_line_number == 0:
        # get nodes...
        for key, value in g_nodeList.items():
            URL = 'http://' + key + ':' + value + '/node/getNode'
            try:
                res = requests.get(URL)
            except requests.exceptions.ConnectionError:
                continue
            if res.status_code == 200:
                print(res.text)
                tmpNodeLists = json.loads(res.text)
                for node in tmpNodeLists:
                    addNode(node)

    # 2. check if we have a blockchain data file
    last_line_number = len(selectTable(g_bcTableName))
    blockchainList = []
    if last_line_number == 0:
        # get Block Data...
        for key, value in g_nodeList.items():
            URL = 'http://' + key + ':' + value + '/block/getBlockData'
            try:
                res = requests.get(URL)
            except requests.exceptions.ConnectionError:
                continue
            if res.status_code == 200:
                print(res.text)
                tmpbcData = json.loads(res.text)
                for line in tmpbcData:
                    # print(type(line))
                    # index, previousHash, timestamp, data, currentHash, proof
                    block = [line['index'], line['previousHash'], line['timestamp'], line['data'], line['currentHash'],
                             line['proof'], line['fee'], line['siggnature']]
                    blockchainList.append(block)
                try:
                    with open(g_bcFileName, "w", newline='') as file:
                        writer = csv.writer(file)
                        writer.writerows(blockchainList)
                except Exception as e:
                    print("file write error in initSvr() " + e)

    return 1


# This class will handle any incoming request from
# a browser
class myHandler(BaseHTTPRequestHandler):

    # def __init__(self, request, client_address, server):
    #    BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    # Handler for the GET requests
    def do_GET(self):
        data = []  # response json data
        if None != re.search('/block/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/block/getBlockData', self.path):
                # TODO: range return (~/block/getBlockData?from=1&to=300)
                # queryString = urlparse(self.path).query.split('&')

                block = readBlockchain(g_bcTableName)

                if len(block) == 0:
                    print("No Block Exists")
                    data.append("no data exists")
                else:
                    for i in range(len(block)):
                        Dict = {'no': str(block.no[i]), 'previoushash': block.previoushash[i],
                                'timestamp': block.timestamp[i], 'data': block.data[i],
                                'currenthash': block.currenthash[i], 'proof': str(block.proof[i]),
                                'fee': str(block.fee[i]), 'signature': block.signature[i]}
                        print(Dict)
                        data.append(Dict)

                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))

            elif None != re.search('/block/generateBlock', self.path):
                t = threading.Thread(target=mine)
                t.start()
                data.append("{mining is underway:check later by calling /block/getBlockData}")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))
            else:
                data.append("{info:no such api}")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))


        elif None != re.search('/node/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/node/addNode', self.path):
                queryStr = urlparse(self.path).query.split(':')
                print("client ip : " + self.client_address[0] + " query ip : " + queryStr[0])
                if self.client_address[0] != queryStr[0]:
                    data.append("your ip address doesn't match with the requested parameter")
                else:
                    res = addNode(queryStr)
                    if res == 1:
                        data.append("node added okay")
                    elif res == 0:
                        data.append("caught exception while saving")
                    elif res == -1:
                        data.append("requested node is already exists")
                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))

            elif None != re.search('/node/getNode', self.path):
                importedNodes = readNodes(g_nodelstTableName)

                for i in range(len(importedNodes)):
                    Dict = {'ip': str(importedNodes.ip[i]), 'port': importedNodes.port[i]}
                    print(Dict)
                    data.append(Dict)

                self.wfile.write(bytes(json.dumps(data, sort_keys=True, indent=4), "utf-8"))

        else:

            self.send_response(403)

            self.send_header('Content-Type', 'application/json')

            self.end_headers()

        # ref : https://mafayyaz.wordpress.com/2013/02/08/writing-simple-http-server-in-python-with-rest-and-json/

    def do_POST(self):

        if None != re.search('/block/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            if None != re.search('/block/validateBlock/*', self.path):
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                # print(ctype) #print(pdict)

                if ctype == 'application/json':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    receivedData = post_data.decode('utf-8')
                    print(type(receivedData))
                    tempDict = json.loads(receivedData)  # load your str into a list #print(type(tempDict))
                    if isValidChain(tempDict) == True:
                        tempDict.append("validationResult:normal")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    else:
                        tempDict.append("validationResult:abnormal")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
            elif None != re.search('/block/newtx', self.path):
                ctype, pdict = cgi.parse_header(self.headers['content-type'])
                if ctype == 'application/json':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)
                    receivedData = post_data.decode('utf-8')
                    print(type(receivedData))
                    tempDict = json.loads(receivedData)
                    res = newtx(tempDict)
                    if res == 1:
                        tempDict.append("accepted : it will be mined later")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    elif res == -1:
                        tempDict.append("declined : number of request txData exceeds limitation")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    elif res == -2:
                        tempDict.append("declined : error on data read or write")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
                    else:
                        tempDict.append("error : requested data is abnormal")
                        self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))

        elif None != re.search('/node/*', self.path):
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if None != re.search(g_receiveNewBlock, self.path):  # /node/receiveNewBlock
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                receivedData = post_data.decode('utf-8')
                tempDict = json.loads(receivedData)  # load your str into a list
                print(tempDict)
                res = compareMerge(tempDict)
                if res == -1:  # internal error
                    tempDict.append("internal server error")
                elif res == -2:  # block chain info incorrect
                    tempDict.append("block chain info incorrect")
                elif res == 1:  # normal
                    tempDict.append("accepted")
                elif res == 2:  # identical
                    tempDict.append("already updated")
                elif res == 3:  # we have a longer chain
                    tempDict.append("we have a longer chain")
                self.wfile.write(bytes(json.dumps(tempDict), "utf-8"))
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

        return


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""


try:

    # Create a web server and define the handler to manage the
    # incoming request
    # server = HTTPServer(('', PORT_NUMBER), myHandler)
    server = ThreadedHTTPServer(('', PORT_NUMBER), myHandler)
    print('Started httpserver on port ', PORT_NUMBER)

    initSvr()
    # Wait forever for incoming http requests
    server.serve_forever()

except (KeyboardInterrupt, Exception) as e:
    print('^C received, shutting down the web server')
    print(e)
    server.socket.close()