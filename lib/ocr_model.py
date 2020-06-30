"""
Copyright (c) 2019-present NAVER Corp.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import torch.nn as nn

from modules.transformation import TPS_SpatialTransformerNetwork
from modules.feature_extraction import VGG_FeatureExtractor, RCNN_FeatureExtractor, ResNet_FeatureExtractor
from modules.sequence_modeling import BidirectionalLSTM
from modules.prediction import Attention


class Model(nn.Module):

    def __init__(self, opt):
        super(Model, self).__init__()
        self.opt = opt
        self.stages = {'Trans': opt.recognition_Transformation, 'Feat': opt.recognition_FeatureExtraction,
                       'Seq': opt.recognition_SequenceModeling, 'Pred': opt.recognition_Prediction}

        """ Transformation """
        if opt.recognition_Transformation == 'TPS':
            self.Transformation = TPS_SpatialTransformerNetwork(
                F=opt.recognition_num_fiducial, I_size=(opt.recognition_imgH, opt.recognition_imgW), I_r_size=(opt.recognition_imgH, opt.recognition_imgW), I_channel_num=opt.recognition_input_channel)
        else:
            print('No Transformation module specified')

        """ FeatureExtraction """
        if opt.recognition_FeatureExtraction == 'VGG':
            self.FeatureExtraction = VGG_FeatureExtractor(opt.recognition_input_channel, opt.recognition_output_channel)
        elif opt.recognition_FeatureExtraction == 'RCNN':
            self.FeatureExtraction = RCNN_FeatureExtractor(opt.recognition_input_channel, opt.recognition_output_channel)
        elif opt.recognition_FeatureExtraction == 'ResNet':
            self.FeatureExtraction = ResNet_FeatureExtractor(opt.recognition_input_channel, opt.recognition_output_channel)
        else:
            raise Exception('No FeatureExtraction module specified')
        self.FeatureExtraction_output = opt.recognition_output_channel  # int(imgH/16-1) * 512
        self.AdaptiveAvgPool = nn.AdaptiveAvgPool2d((None, 1))  # Transform final (imgH/16-1) -> 1

        """ Sequence modeling"""
        if opt.recognition_SequenceModeling == 'BiLSTM':
            self.SequenceModeling = nn.Sequential(
                BidirectionalLSTM(self.FeatureExtraction_output, opt.recognition_hidden_size, opt.recognition_hidden_size),
                BidirectionalLSTM(opt.recognition_hidden_size, opt.recognition_hidden_size, opt.recognition_hidden_size))
            self.SequenceModeling_output = opt.recognition_hidden_size
        else:
            print('No SequenceModeling module specified')
            self.SequenceModeling_output = self.FeatureExtraction_output

        """ Prediction """
        if opt.recognition_Prediction == 'CTC':
            self.Prediction = nn.Linear(self.SequenceModeling_output, opt.recognition_num_class)
        elif opt.recognition_Prediction == 'Attn':
            self.Prediction = Attention(self.SequenceModeling_output, opt.recognition_hidden_size, opt.recognition_num_class)
        else:
            raise Exception('Prediction is neither CTC or Attn')

    def forward(self, input, text, is_train=True):
        """ Transformation stage """
        if not self.stages['Trans'] == "None":
            input = self.Transformation(input)

        """ Feature extraction stage """
        visual_feature = self.FeatureExtraction(input)
        visual_feature = self.AdaptiveAvgPool(visual_feature.permute(0, 3, 1, 2))  # [b, c, h, w] -> [b, w, c, h]
        visual_feature = visual_feature.squeeze(3)

        """ Sequence modeling stage """
        if self.stages['Seq'] == 'BiLSTM':
            contextual_feature = self.SequenceModeling(visual_feature)
        else:
            contextual_feature = visual_feature  # for convenience. this is NOT contextually modeled by BiLSTM

        """ Prediction stage """
        if self.stages['Pred'] == 'CTC':
            prediction = self.Prediction(contextual_feature.contiguous())
        else:
            prediction = self.Prediction(contextual_feature.contiguous(), text, is_train, batch_max_length=self.opt.recognition_batch_max_length)

        return prediction
