import gc
import math
import os
import uuid
from random import randint

import numpy as np
import xgboost as xgb
from scipy.stats.mstats import gmean

from utils.helpers import cleanup, print_experiment, generate_pairs, get_models


def get_trajectory(seed, index, trajectory_length):
    path = "tmp/"
    npy_train = path + str(seed) + '_' + str(trajectory_length) + '.npy'

    return np.load(npy_train, 'r', allow_pickle=True)[index]


def get_trajectory_test(seed, index, trajectory_length):
    path = "tmp/"
    npy_test = path + str(seed) + '_' + str(trajectory_length) + '_test.npy'

    return np.load(npy_test, 'r', allow_pickle=True)[index]


def create_sets(seeds, attack_training_size, timesteps, trajectory_length, num_predictions, dimension):
    path = "tmp_plks/"
    if not os.path.exists(path):
        os.mkdir(path)

    train_size = math.floor(attack_training_size / (10 / 8))
    eval_size = math.floor(attack_training_size / (10 / 2))
    num_traj_per_model = int(timesteps / trajectory_length)
    total_pairs_needed = attack_training_size + num_predictions
    data_length = 2 * (trajectory_length * dimension)

    data_train = np.empty([0, data_length])
    data_eval = np.empty([0, data_length])
    labels_train = np.empty(train_size, dtype=int)
    labels_eval = np.empty(eval_size, dtype=int)
    data_test = np.empty([0, data_length])
    labels_test = []
    train_pairs, test_pairs = generate_pairs(total_pairs_needed, len(seeds) * num_traj_per_model, num_predictions,
                                             attack_training_size)

    d_test = str(uuid.uuid4())
    d_t = str(uuid.uuid4())
    l_t = str(uuid.uuid4())
    d_e = str(uuid.uuid4())
    l_e = str(uuid.uuid4())

    # save test pairs
    indx = 0
    for x_i, y_i in test_pairs:
        x_model, y_model, same_set, index_x, index_y = get_models(x_i, y_i, num_traj_per_model)
        seed_x = seeds[x_model]
        seed_y = seeds[y_model]
        data_test = np.insert(data_test, indx,
                              np.concatenate((get_trajectory(seed_x, index_x, trajectory_length),
                                              get_trajectory_test(seed_y, index_y, trajectory_length))), axis=0)

        if same_set:
            labels_test.append(1)
        else:
            labels_test.append(0)

        indx += 1

    np.save(path + d_test + '.npy', data_test)

    del test_pairs, data_test
    gc.collect()
    print("saved test pairs")

    # save train pairs
    indx = 0
    for x_i, y_i in train_pairs:
        if indx < train_size:
            x_model, y_model, same_set, index_x, index_y = get_models(x_i, y_i, num_traj_per_model)
            seed_x = seeds[x_model - 1]
            seed_y = seeds[y_model - 1]
            data_train = np.insert(data_train, indx, np.concatenate(
                (get_trajectory(seed_x, index_x, trajectory_length),
                 get_trajectory_test(seed_y, index_y, trajectory_length))),
                                   axis=0)

            if same_set:
                labels_train.put(indx, 1)
            else:
                labels_train.put(indx, 0)

        else:
            break

        indx += 1

    np.save(path + d_t + '.npy', data_train)
    np.save(path + l_t + '.npy', labels_train)

    del data_train, labels_train
    gc.collect()
    print("saved train pairs")

    # save eval pairs
    insrt = 0
    while indx < attack_training_size:
        x_i, y_i = train_pairs[indx]
        x_model, y_model, same_set, index_x, index_y = get_models(x_i, y_i, num_traj_per_model)
        seed_x = seeds[x_model - 1]
        seed_y = seeds[y_model - 1]
        data_eval = np.insert(data_eval, insrt, np.concatenate(
            (get_trajectory(seed_x, index_x, trajectory_length),
             get_trajectory_test(seed_y, index_y, trajectory_length))),
                              axis=0)

        if same_set:
            labels_eval.put(insrt, 1)
        else:
            labels_eval.put(insrt, 0)

        indx += 1
        insrt += 1

    np.save(path + d_e + '.npy', data_eval)
    np.save(path + l_e + '.npy', labels_eval)

    del data_eval, labels_eval
    gc.collect()
    print("saved eval pairs")

    return d_t, l_t, d_e, l_e, d_test, labels_test


def logger(baseline, false_negatives_bl, false_positives_bl, rmse, accuracy, false_negatives, false_positives):
    print("Baseline Accuracy: ", baseline)
    print("Precision BL: ", false_negatives_bl)
    print("Recall BL: ", false_positives_bl)
    print("Attack Classifier Accuracy: ", accuracy)
    print("Precision: ", false_negatives)
    print("Recall: ", false_positives)
    print("Root MSE: ", rmse)
    print("****************************")


def rsme(errors):
    return np.sqrt(gmean(np.square(errors)))


def calc_errors(classifier_predictions, labels_test, threshold, num_predictions):
    errors = []
    for i in range(num_predictions):
        e_i = (labels_test[i] - classifier_predictions[i]) / (labels_test[i] - threshold)
        errors.append(e_i)

    return errors


def baseline_accuracy(labels_test, num_predictions):
    num_correct = 0
    false_positives = 0
    false_negatives = 0
    for i in range(num_predictions):
        guess = randint(0, 1)

        # if theyre the same
        if guess == labels_test[i]:
            num_correct += 1
        # said out was acutually in
        elif guess == 0 and labels_test[i] == 1:
            false_negatives += 1
        elif guess == 1 and labels_test[i] == 0:
            false_positives += 1

    return output_prec_recall((num_correct / num_predictions), (false_negatives / num_predictions),
                              (false_positives / num_predictions))


def accuracy_report(classifier_predictions, labels_test, threshold, num_predictions):
    num_correct = 0
    false_positives = 0
    false_negatives = 0
    for i in range(num_predictions):
        if classifier_predictions[i] >= threshold and labels_test[i] is 1:
            num_correct += 1
        elif classifier_predictions[i] < threshold and labels_test[i] is 0:
            num_correct += 1

        # false negative (classifier is saying out but labels say in)
        elif classifier_predictions[i] < threshold and labels_test[i] is 1:
            false_negatives += 1

        # false positive (classifier is saying in but labels say out)
        elif classifier_predictions[i] >= threshold and labels_test[i] is 0:
            false_positives += 1

    return output_prec_recall((num_correct / num_predictions), (false_negatives / num_predictions),
                              (false_positives / num_predictions))


def output_prec_recall(acc, fn, fp):
    tp = int(500 * acc)
    fn = int(500 * fn)
    fp = int(500 * fp)

    prec = tp / (tp + fp)
    recall = tp / (tp + fn)

    return acc, round(prec, 3), round(recall, 3)


def generate_metrics(classifier_predictions, labels_test, threshold, num_predictions):
    accuracy, false_negatives, false_positives = accuracy_report(classifier_predictions, labels_test, threshold,
                                                                 num_predictions)
    baseline, false_negatives_bl, false_positives_bl = baseline_accuracy(labels_test, num_predictions)
    RMSE_e_i = rsme(calc_errors(classifier_predictions, labels_test, threshold, num_predictions))

    logger(baseline, false_negatives_bl, false_positives_bl, RMSE_e_i, accuracy, false_negatives, false_positives)
    return baseline, false_negatives_bl, false_positives_bl, RMSE_e_i, accuracy, false_negatives, false_positives


def train_classifier(xgb_train, xgb_eval):
    num_round = 150
    param = {'eta': '0.2',
             'n_estimators': '5000',
             'max_depth': 20,
             'objective': 'reg:logistic',
             'eval_metric': ['logloss', 'error', 'rmse']}

    watch_list = [(xgb_eval, 'eval'), (xgb_train, 'train')]
    evals_result = {}
    print("training classifier")
    return xgb.train(param, xgb_train, num_round, watch_list, evals_result=evals_result)


def train_attack_model_v2(environment, threshold, trajectory_length, seeds, attack_model_size, test_size, timesteps,
                          dimension):
    path = "tmp_plks/"
    d_t, l_t, d_e, l_e, d_test, labels_test = create_sets(seeds, attack_model_size, timesteps, trajectory_length,
                                                          test_size, dimension)

    # xgb_t, xgb_e, xgb_test = create_xgb_train_test_eval(d_t, l_t, d_e, l_e, d_test)
    attack_classifier = train_classifier(xgb.DMatrix(np.load(path + d_t + '.npy'), label=np.load(path + l_t + '.npy')),
                                         xgb.DMatrix(np.load(path + d_e + '.npy'), label=np.load(path + l_e + '.npy')))

    print("training finished --> generating predictions")
    xgb_testing = xgb.DMatrix(np.load(path + d_test + '.npy'))
    classifier_predictions = attack_classifier.predict(xgb_testing)

    cleanup([d_t, l_t, d_e, l_e, d_test], ["1"])

    print_experiment(environment, len(seeds), threshold, trajectory_length,
                     attack_model_size)

    return generate_metrics(classifier_predictions, labels_test, threshold, test_size)
