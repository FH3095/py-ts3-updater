#!/usr/bin/env python3

import sys,shutil,pathlib,os
import json,configparser
import urllib.parse,tempfile,requests,random,hashlib
import tarfile,subprocess

def downloadFile(mirror, tempFile):
	with requests.get(mirror, stream=True) as request:
		request.raise_for_status()
		shutil.copyfileobj(request.raw,tempFile)

def downloadFileFromAnyMirror(mirrors, expectedChecksum):
	for mirror in mirrors:
		fileSuffix = "_" + pathlib.Path(urllib.parse.urlparse(mirror).path).name
		tempFilePath = None
		try:
			with tempfile.NamedTemporaryFile(mode="wb",prefix="ts3update_",suffix=fileSuffix,delete=False) as tempFile:
				tempFilePath = pathlib.Path(tempFile.name)
				print("Download from " + mirror)
				downloadFile(mirror, tempFile)
			with open(tempFilePath,mode="rb") as tempFile:
				sha256 = hashlib.sha256()
				for fileBytes in iter(lambda: tempFile.read(8192),b""):
					sha256.update(fileBytes)
				actualChecksum = sha256.hexdigest().lower()
				if expectedChecksum.lower() != actualChecksum:
					raise RuntimeError("Expected checksum " + expectedChecksum + " doesnt match actual checksum "+actualChecksum)
				else:
					print("Download successfull and verified")
					return tempFilePath
		except Exception as error:
			print("Cant download file from " + mirror + ": " + str(error))
			tempFilePath.unlink()
	
	raise RuntimeError("Cant download file")

def tarFileMemberIterator(tarFile, commonPrefix):
	commonPrefixLen = len(commonPrefix)
	for member in tarFile.getmembers():
		if member.path.startswith(commonPrefix):
			member.path = member.path[commonPrefixLen:]
			yield member

### Parse config

config = configparser.ConfigParser()
with open("config.ini", encoding="utf-8") as configFile:
	config.read_file(configFile)

data = configparser.ConfigParser()
with open("data.ini", encoding="utf-8") as dataFile:
	data.read_file(dataFile)


### Fetch JSON
with requests.get(config["UPDATE"]["JSON_URL"]) as request:
	request.raise_for_status()
	json = request.json()
json = json[config["UPDATE"]["OS"]][config["UPDATE"]["ARCH"]]

currentVersion = json["version"]
oldVersion = data["DATA"]["CURRENT_VERSION"]

if currentVersion == oldVersion:
	sys.exit(0)

print("New version available. Old version: " + oldVersion + " New Version: " + currentVersion)

ts3Folder = pathlib.Path(config["TS"]["FOLDER"]).absolute()
ts3ServerScript = ts3Folder.joinpath("ts3server_startscript.sh")
ts3UpdateInProgressFile = ts3Folder.joinpath("ts3update_in_progress.txt")
ts3UpdateInProgressFile.write_text("yes\n")

try:
	subprocess.run([str(ts3ServerScript), "stop"], capture_output=True, text=True, check=True)
	mirrors = (list(json["mirrors"].values()))
	#random.shuffle(mirrors)
	tempFilePath = downloadFileFromAnyMirror(mirrors, json["checksum"])
	try:
		if '.tar' not in tempFilePath.name:
			raise RuntimeError("Cant handle non-tar files yet")
		with tarfile.open(tempFilePath) as tarFile:
			rootDir = os.path.commonprefix(tarFile.getnames())
			rootDir = rootDir.split("/", 1)[0] + "/"
			print("Extracting folder " + rootDir + " from archive-file to " + str(ts3Folder))
			tarFile.extractall(path=ts3Folder,members=tarFileMemberIterator(tarFile,rootDir))
	finally:
		tempFilePath.unlink()
except subprocess.CalledProcessError as scriptError:
	print(str(scriptError))
	print("Output:")
	print(scriptError.output)
	raise
finally:
	ts3UpdateInProgressFile.unlink()


#data["DATA"]["CURRENT_VERSION"] = "0."+currentVersion
data["DATA"]["CURRENT_VERSION"] = currentVersion
with open("data.ini", mode="wt", encoding="utf-8") as dataFile:
	data.write(dataFile)

print("Update to " + currentVersion + " successfull")
