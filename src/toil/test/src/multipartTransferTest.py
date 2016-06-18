# Copyright (C) 2015 UCSC Computational Genomics Lab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

import io
import traceback
import uuid
from contextlib import contextmanager, closing
import collections
from unittest import skip

import math

import boto
import os
from bd2k.util.exceptions import panic
from concurrent.futures import ThreadPoolExecutor
from psutil import cpu_count
from toil.jobStores.aws.utils import region_to_bucket_location
from toil.test import ToilTest, make_tests
from toil.jobStores.aws.jobStore import copyKeyMultipart


partSize = 2**20 * 5


@contextmanager
def openS3(keySize=None):
    """
    Creates an AWS bucket. If keySize is given a key of random bytes is created and its handle
    is yielded. If no keySize is given an empty bucket handle is yielded. The bucket and all
    created keys are cleaned up automatically.

    :param int keySize: Size of key to be created.
    """
    if keySize < 0 and keySize is not None:
        raise ValueError('Key size must be greater than zero')
    with closing(boto.s3.connect_to_region(AWSMultipartCopyTest.region)) as s3:
        bucket = s3.create_bucket('multipart-transfer-test-%s' % uuid.uuid4(),
                                  location=region_to_bucket_location('us-west-2'))
        keyName = 'test'
        keySize = keySize or -1
        if keySize < 0:
            yield bucket
        else:
            key = bucket.new_key(keyName)
            content = os.urandom(keySize)
            key.set_contents_from_string(content)

            yield bucket.get_key(keyName)
        for key in bucket.list():
            key.delete()
        bucket.delete()


class AWSMultipartCopyTest(ToilTest):
    region = 'us-west-2'

    def setUp(self):
        super(AWSMultipartCopyTest, self).setUp()

    @classmethod
    def makeTests(self):
        def multipartCopy(self, threadPoolSize):
            # key size is padded to ensure some threads are reused
            keySize = int(math.ceil((threadPoolSize * partSize) * 1.3))
            with openS3(keySize) as srcKey:
                with openS3() as dstBucket:
                    copyKeyMultipart(srcKey, dstBucket, 'test')
                    self.assertEqual(srcKey.get_contents_as_string(),
                                     dstBucket.get_key('test').get_contents_as_string())

        make_tests(multipartCopy, targetClass=AWSMultipartCopyTest,
                   threadPoolSize={str(x): x for x in (1, 2, 16)})

AWSMultipartCopyTest.makeTests()
