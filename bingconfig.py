#
# Signup at
#  https://datamarket.azure.com/account/keys
#
# Add access to the Bing api at
#  https://datamarket.azure.com/dataset/bing/search
#
# Add access to web search api at
#  https://datamarket.azure.com/dataset/8818F55E-2FE5-4CE3-A617-0B8BA8419F65
#
# Get your API key from
#  https://datamarket.azure.com/account/keys
#
# Add key below and call
#  import bing, bingconf
#  bing.setKey(bingconfig.key)
#  urls = bing.search("nyan cat")

key = None

# When you have added your key, type the following command so you never
# accidentaly push your key to Github:
#
#  git update-index --assume-unchanged FILENAME_TO_IGNORE bingconfig.py
