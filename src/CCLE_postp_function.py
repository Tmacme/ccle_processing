# Jérémie Kalfon
# for BroadInsitute
# in 2019


####
#
# HELPER FUNC  ######################################
#
#
import pdb
import pandas as pd
import numpy as np
from taigapy import TaigaClient
tc = TaigaClient()
import os
import re # for re.split

CHROMLIST = ['chr1', 'chr2', 'chr3', 'chr4', 'chr5', 'chr6', 'chr7', 'chr8',
             'chr9', 'chr10', 'chr11', 'chr12', 'chr13', 'chr14', 'chr15',
             'chr16', 'chr17', 'chr18', 'chr19', 'chr20',
             'chr21', 'chr22', 'chrX']


extract_defaults = {
    'name': 'sample_alias',
    'bai': 'crai_or_bai_path',
    'bam': 'cram_or_bam_path',
    'source': 'source',
    'id': 'individual_alias',
    'participant': 'individual_alias',
    'bait_set': 'bait_set',
    'hs_hs_library_size': 'hs_hs_library_size',
    'hs_het_snp_sensitivity': 'hs_het_snp_sensitivity',
    'hs_mean_bait_coverage': 'hs_mean_bait_coverage',
    'hs_mean_target_coverage': 'hs_mean_target_coverage',
    'hs_on_target_bases': 'hs_on_target_bases',
    'total_reads': 'total_reads',
    'release_date': 'release_date',
    'mean_depth': 'mean_depth'
}


def read(filename):
  f = open(filename, 'r')
  x = f.read().splitlines()
  f.close()
  return x

def get_all_sizes(folder, suffix):
  # get ls of all files in the folder with the specified suffix
  samples = os.popen('gsutil -m ls -al ' + folder + '**.' + suffix).read().split('\n')
  # compute size filepath
  sizes = {'gs://' + val.split('gs://')[1].split('#')[0]: int(re.split("\d{4}-\d{2}-\d{2}", val)[0]) for val in samples[:-2]}
  names = {}
  for k, val in sizes.items():
    if val in names:
      names[val].append(k)
    else:
      names[val] = [k]
  if names == {}:
    # we didn't find any valid file paths
    print("We didn't find any valid file paths in folder: " + str(folder))
  return names

def get_GS_file_sizes(file_list):
  # get size of each file in the input list of files (assumed to be in google storage)
  names = {}
  for file in file_list:
    samples = os.popen('gsutil -m ls -al ' + file).read().split('\n')
    # compute size filepath
    sizes = {'gs://' + val.split('gs://')[1].split('#')[0]: int(re.split("\d{4}-\d{2}-\d{2}", val)[0]) for val in samples[:-2]}
    for k, val in sizes.items():
      if val in names:
        names[val].append(k)
      else:
        names[val] = [k]
  if names == {}:
    # we didn't find any valid file paths
    print("We didn't find any valid file paths in the list of files: " + str(file_list))
  return names

def createDatasetWithNewCellLines(wto, samplesetname,
                                  wmfroms, sources,
                                  forcekeep=[], addonly=[], match='ACH', other_to_add=[], extract={}, extract_defaults=extract_defaults,
                                  participantslicepos=10, accept_unknowntypes=False,
                                  gsfolderto=None, dry_run=False):
  """
  ## check: will need to change slicepos based on match;
  ## may have to take diff approach (regex?) for CCLF samples since CCLF sample IDs are not of consistent length
  wto: dalmatian.workspacemanager the workspace where you want to create the tsvs
  samplesetname: String the name of the sample set created by this new set of samples updated
  wfrom1: dalmatian.workspacemanager the workspace where the Samples to add are stored
  source1: the corresponding source name
  Can add as much as one wants
  dry_run: whether to perform a dry run without actually uploading anything to Terra
  forcekeep: list of sample id that you want to keep even if already in the previous workspace (will
  cause an overwrite) NOTE: currently this functionality is broken due to the implementation of checking for duplicates
  addonly: list of sample id that you only want to add
  match: list of substring(s) that has to be matched against the id of the samples to add them
  other_to_add:
  extract: if you want to specify what values should refer to which column names
    dict{    'name':
    'bai':
    'bam':
    'source':
    'id':
    ...}
  extract_defaults: the full default dict to specificy what values should refer to which column names

  """
  refsamples = wto.get_samples()
  refids_full = refsamples['participant'].tolist()
  # do NOT make refids a set; we use the num of occurences as way to determine what number to add to the sample id
  # filter refids to only include those that include the strings in the 'match' argument
  refids = []
  if type(match) is str:
    match = [match]
  for match_substring in match:
    refids += [val[val.index(match_substring):] for val in refids_full if match_substring in val]

  # update extract dict with user-defined values
  for key, value in extract.items():
    if key not in extract_defaults.keys() and key != 'ref_bams':
      print("We did not find the key '" + str(key) + "' in the full extraction dict. This key-value mapping may do nothing...")
  extract_defaults.update(extract)
  extract = extract_defaults

  print("Getting sample infos...")
  if type(sources) is str:
    sources = [sources]
  if type(wmfroms) is str:
    wmfroms = [wmfroms]
  sampless = pd.DataFrame()
  for source, wmfrom in zip(sources, wmfroms):
    broken_bams = []
    samples = wmfrom.get_samples().replace(np.nan, '', regex=True).reset_index()
    # keep samples that contain the match requirement (e.g. ACH for DepMap IDs)
    samples = samples[samples[extract['id']].str.contains('|'.join(match))]
    print("\nThe shape of the sample tsv from " + str(wmfrom) + ": " + str(samples.shape))

    # remove true duplicates from consideration
    print("Identifying any true duplicates by checking file sizes (this runs for each data source)...")
    print("This step can take a while as we need to use gsutil to check the size of each potential duplicate...")
    dups_to_remove = []
    broken_to_remove = []
    for k, rowinfo in samples.iterrows():
      # check for broken bam files; if broken, then remove from consideration
      # need to check for broken filepaths before checking if the sample is in Terra so that we don't add a broken file path for a new participant
      filepath = rowinfo[extract['bam']]
      sample_to_check = os.popen('gsutil -m ls -al ' + filepath).read().split('\n')
      if sample_to_check  == ['']:
          # this bam file doesn't exist at this filepath
          print("The bam file path we have in data workspace is broken, so we will remove it from consideration:\n " + str(filepath))
          broken_bams += [filepath]
          broken_to_remove += [rowinfo[extract['bam']]]

      # if this sample is in Terra already, need to check for duplicates
      if rowinfo[extract['id']][0:participantslicepos] in refids:
        # better regex for yyyy-mm-dd ([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))
        sample_size = {'gs://' + val.split('gs://')[1].split('#')[0]: int(re.split("\d{4}-\d{2}-\d{2}", val)[0]) for val in sample_to_check[:-2]}
        for file, val in sample_size.items():
          # get list of the pre-existing entries for the same participant (only include if the bam file path is valid; aka the filepath exists)
          same_participant = refsamples[refsamples['participant'] == rowinfo[extract['id']][0:participantslicepos]]
          same_participant_bams = []
          for samp, entry in same_participant.iterrows():
            if entry[extract['ref_bams']] != 'NA':
              try:
                os.system('gsutil -m ls -al ' + entry[extract['ref_bams']])
                same_participant_bams += [entry[extract['ref_bams']]]
              except CommandException:
                  # this bam file doesn't exist at this filepath
                  print("The bam file path for " + str(rowinfo[extract['id']]) + " in the processing workspace is broken:\n " + str(entry[extract['ref_bams']]))
                  broken_bams += [entry[extract['ref_bams']]]
          if len(same_participant_bams) == 0:
              # in this case, had no valid bam paths in the processing workspace, so no potential for duplicates
              continue

          # get sizes of these pre-existing bams
          same_participant_bams_sizes = get_GS_file_sizes(same_participant_bams)
          # if new sample size is in this dict of sizes, then the sample is a duplicate
          if val in same_participant_bams_sizes:
            dups_to_remove += [rowinfo[extract['bam']]]
          # print("The new sample: " + str(file))
          # print("The pre-existing sample of the same size: " + str(same_participant_bams_sizes[val]))

    # check: currently, below lines prevent forcekeep from working on true duplicates (aka same size  file). Need to think about how to bring back the forcekeep functionality
    print("Dups from " + str(wmfrom) + " has len " + str(len(dups_to_remove)) + ":\n " + str(dups_to_remove))
    print("Len of samples before removal: " + str(len(samples)))
    # remove the duplicates from consideration
    samples = samples[(~samples[extract['bam']].isin(dups_to_remove))]
    # remove the samples with broken bam filepaths from consideration
    samples = samples[(~samples[extract['bam']].isin(broken_to_remove))]
    samples.reset_index(drop=True, inplace=True)
    print("Len of samples after removal: " + str(len(samples)))

    # add number to sample ID so runs of same participant have unique sample ID
    new_samples = samples[extract['id']].str.slice(0, participantslicepos)
    for iSample in range(len(new_samples)):
      new_sample_id = new_samples.values[iSample]
      num_in_workspace = refids.count(new_sample_id)
      # need to keep track of whether we're adding more than one new entry for a given sample id
      num_per_sample_dict = {}
      try:
        num_already_seen_here = num_per_sample_dict[new_sample_id]
        num_to_add = num_in_workspace + num_already_seen_here + 1
        num_per_sample_dict[new_sample_id] += 1
      except:
        num_per_sample_dict[new_sample_id] = 1
        num_to_add = num_in_workspace + 1

      # update the sample dataframe with the new sample ID
      samples[extract['id']][iSample] = new_sample_id + '_' + str(num_to_add)

    if len(addonly) > 0:
      samples = samples[samples[extract['id']].isin(addonly)]

    samples[extract['source']] = source
    if 'sample_type' in samples.columns:
      if not accept_unknowntypes:
        samples = samples[samples['sample_type'].isin(['Tumor'])]
    sampless = pd.concat([sampless, samples], sort=False)

    print('These bam file path do not exist: ' + str(broken_bams))
  # ## currently, we don't do anything with notfound. Therefore addonly functionality is broken.
  # notfound = set(addonly) - set(sampless.index.tolist())
  # if len(notfound) > 0:
  #   # samples not found in the wto workspace so will be adding them now
  #   print('we did not find:' + str(notfound))

  sample_ids = []
  # to do the download to the new dataspace
  if not dry_run:
    if gsfolderto is not None:
      for i, val in sampless.iterrows():
        if os.system('gsutil ls ' + val[extract['bam']]) != 256:
          res = os.system('gsutil cp ' + val[extract['bam']] + ' ' + val[extract['bai']] + ' ' + gsfolderto)
          if res == 256:
            sampless.drop(i)
            print('we got sample ' + str(i) + ' that had nonexistant bam path')
      sampless[extract['bam']] = [gsfolderto + a.split('/')[-1] for a in sampless[extract['bam']]]
      sampless[extract['bai']] = [gsfolderto + a.split('/')[-1] for a in sampless[extract['bai']]]
    print(sampless)
  if len(sampless) == 0:
    raise Exception("no new samples in this matrix")
  for ind, val in sampless.iterrows():
    name = val[extract['id']]
    refsamples = refsamples.append(pd.Series(
        {
            "CCLE_name": val[extract['name']],
            "WES_bai": val[extract['bai']],
            "WES_bam": val[extract['bam']],
            "Source": val[extract['source']],
            "participant": val[extract['participant']][:participantslicepos],

        }, name=name))
    sample_ids.append(name)

  if not dry_run:
    print("uploading new samples")
    wto.upload_samples(refsamples)
    print("creating a sample set")
    wto.update_sample_set(sample_set_id=samplesetname, sample_ids=sample_ids)
  return sample_ids, refsamples['WES_bam'].values, refsamples

#####################
# VALIDATION
#####################


def checkAmountOfSegments(segmentcn, thresh=850):
  """
  if there is too many segments, something might be wrong
  segmentcn: segment dataframe
  thresh: max ok amount
  """
  segmentcn = renameColumns(segmentcn)
  celllines = set(segmentcn["DepMap_ID"].tolist())
  for cellline in celllines:
    if segmentcn[segmentcn["DepMap_ID"] == cellline].shape[0] > thresh:
      print(cellline, segmentcn[segmentcn["DepMap_ID"] == cellline].shape[0])


def checkGeneChangeAccrossAll(genecn, thresh=1.5):
  """
  genecn: gene cn data frame
  thresh: threshold in logfold change accross all of them
  """
  pos = genecn.where((genecn > thresh) & (genecn < 1 / thresh), 0).all(0)
  return pos.loc[pos == True].index.values


def renameColumns(df):
  return(df.rename(columns={'Sample': 'DepMap_ID', 'CONTIG': 'Chromosome', 'START': 'Start',
                            'END': 'End', 'seqnames': 'Chromosome', 'start': 'Start', 'end': 'End'}))


def checkDifferencesWESWGS(segmentcn_wes, segmentcn_wgs, chromlist=CHROMLIST):
  """
  if the similarity between WES and WGS on same cell line is different there might be problems.
  """

  # function for overlap between two segments 1D
  def overlap(min1, max1, min2, max2):
    return max(0, min(max1, max2) - max(min1, min2))

  segmentcn_wes = renameColumns(segmentcn_wes)
  segmentcn_wgs = renameColumns(segmentcn_wgs)

  common = set(segmentcn_wgs["DepMap_ID"].tolist()) & set(segmentcn_wes["DepMap_ID"].tolist())
  print('anlaysing on ' + str(common) + " common cell lines")
  segmentcn_wes = segmentcn_wes.loc[segmentcn_wes["DepMap_ID"].isin(common)]
  segmentcn_wgs = segmentcn_wgs.loc[segmentcn_wgs["DepMap_ID"].isin(common)]
  if not segmentcn_wes['Chromosome'].iloc[0] in chromlist:
    print(segmentcn_wes['Chromosome'].iloc[0])
    print("assuming that the values are of type 1,2.. converting to chr1,chr2...")
    segmentcn_wes['Chromosome'] = 'chr' + segmentcn_wes['Chromosome'].astype(str)
  if not segmentcn_wgs['Chromosome'].iloc[0] in chromlist:
    print(segmentcn_wgs['Chromosome'].iloc[0])
    print("assuming that the values are of type 1,2.. converting to chr1,chr2...")
    segmentcn_wgs['Chromosome'] = 'chr' + segmentcn_wgs['Chromosome'].astype(str)

  counts = []
  for name in common:
    count = 0
    for chrom in chromlist:
      i = 0
      cnwes = segmentcn_wes[segmentcn_wes["DepMap_ID"] == name][
          segmentcn_wes["Chromosome"] == chrom][['Start', 'End', 'Segment_Mean']].values
      cnwgs = segmentcn_wgs[segmentcn_wgs["DepMap_ID"] == name][
          segmentcn_wgs["Chromosome"] == chrom][['Start', 'End', 'Segment_Mean']].values
      for val in cnwes:
        if not overlap(val[0], val[1], cnwgs[i][0], cnwgs[i][1]):
          count += 1
          if cnwgs[i][0] > val[1]:
            continue
          elif cnwgs[i][1] < val[0]:
            while cnwgs[i][1] < val[0]:
              i += 1
              count += 1
        else:
          if abs(val[2] - cnwgs[i][2]) > 0.2:
            count += 1
    if count > 500:
      print(name, count)


def addToMainFusion(input_filenames, main_filename):
  """

  input_filenames: a set of filepath to input the files should be c|tsv from Terra fusion pipeline
  main_filename: a filepath to input the files should be c|tsv from Terra aggregation pipeline
  """
  maindata = pd.read_csv(main_filename, sep='\t')
  if '.' in maindata["DepMap_ID"][0]:
    maindata["DepMap_ID"] = [i[0] for i in maindata["DepMap_ID"].str.split('.').tolist()]
  samples = set(maindata["DepMap_ID"].tolist())
  with open(main_filename, 'a') as f:
    for input_filename in input_filenames:
      df = pd.read_csv(input_filename, sep='\t')
      input_filename = input_filename.split('/')[-1].split('.')[0]
      if input_filename in samples:
        print(input_filename + " is Already in main fusions")
      df['DepMap_ID'] = pd.Series([input_filename] * len(df.index.tolist()), index=df.index)
      cols = df.columns.tolist()
      cols = cols[-1:] + cols[:-1]
      df = df[cols]
      df.to_csv(f, header=False, sep='\t', index=False)


def addSamplesRSEMToMain(input_filenames, main_filename):
  """
  input_filenames: a list of dict like file path in Terra gs://, outputs from the rsem pipeline
  main_filename: a dict like file paths in Terra gs://, outputs from rsem aggregate
  """
  genes_count = pd.read_csv('temp/' + main_filename['rsem_genes_expected_count'].split('/')[-1],
                            sep='\t', compression='gzip')
  transcripts_tpm = pd.read_csv('temp/' + main_filename['rsem_transcripts_tpm'].split('/')[-1],
                                sep='\t', compression='gzip')
  genes_tpm = pd.read_csv('temp/' + main_filename['rsem_genes_tpm'].split('/')[-1],
                          sep='\t', compression='gzip')

  for input_filename in input_filenames:
    name = input_filename['rsem_genes'].split('/')[-1].split('.')[0].split('_')[-1]
    rsem_genes = pd.read_csv('temp/' + input_filename['rsem_genes'].split('/')[-1], sep='\t')
    rsem_transcripts = pd.read_csv('temp/' + input_filename['rsem_isoforms'].split('/')[-1], sep='\t')
    genes_count[name] = pd.Series(rsem_genes['expected_count'], index=rsem_genes.index)
    transcripts_tpm[name] = pd.Series(rsem_transcripts['TPM'], index=rsem_transcripts.index)
    genes_tpm[name] = pd.Series(rsem_genes['TPM'], index=rsem_genes.index)

  genes_count.to_csv('temp/' + main_filename['rsem_genes_expected_count'].split('/')[-1], sep='\t',
                     index=False, index_label=False, compression='gzip')
  transcripts_tpm.to_csv('temp/' + main_filename['rsem_transcripts_tpm'].split('/')[-1], sep='\t',
                         index=False, index_label=False, compression='gzip')
  genes_tpm.to_csv('temp/' + main_filename['rsem_genes_tpm'].split('/')[-1], sep='\t',
                   index=False, index_label=False, compression='gzip')


def ExtractStarQualityInfo(samplesetname, wm):
  """
  """
  a = wm.get_samples().loc[wm.get_sample_sets().loc[samplesetname].samples].star_logs
  for i, sample in enumerate(a):
    if sample is None:
      print("no log file found for: " + a.index[i])
    for log in sample:
      if 'final.out' in log:
        print("copying " + a.index[i])
        os.system('gsutil cp ' + log + ' temp/')
  os.system("cat temp/*.Log.final.out > temp/" + samplesetname + ".txt")
  os.system("rm temp/*.Log.final.out")


def AddToVirtual(virtualname, folderfrom, files):
  assert type(files[0]) is tuple
  versiona = max([int(i['name']) for i in tc.get_dataset_metadata(folderfrom)['versions']])
  versionb = max([int(i['name']) for i in tc.get_dataset_metadata(virtualname)['versions']])
  keep = [(i['name'], i['underlying_file_id']) for i in tc.get_dataset_metadata(
      virtualname, version=versionb)['datasetVersion']['datafiles']]

  for i, val in enumerate(files):
    files[i] = (val[0], folderfrom + '.' + str(versiona) + '/' + val[1])
    for j, v in enumerate(keep):
      if val[0] == v[0]:
        keep.pop(j)

  files.extend(keep)
  tc.update_dataset(dataset_permaname=virtualname, add_taiga_ids=files, upload_file_path_dict={})


def compareToCuratedGS(url, sample, samplesetname, colname = 'CN New to internal'):
  from gsheets import Sheets
  sheets = Sheets.from_files('~/.client_secret.json', '~/.storage.json')
  # Cell Line Profiling Status google sheet
  gsheet = sheets.get(url).sheets[0].to_frame()
  gsheet.index = gsheet['DepMap ID']
  new_cn = gsheet[gsheet[colname] == samplesetname+'tent']
  data_not_ready_cn = gsheet[gsheet[colname] == 'no data yet']

  # these are the "new" samples discovered by our function, createDatasetsFromNewCellLines
  sample_ids = [id[0:10] for id in sample]
  print("We found data for " + str(len(sorted(sample))) + " samples.\n")

  print("Sanity check: Since we have the tacked on number, we should only have 1 each per sample ID:\n")
  from collections import Counter
  Counter(sample)

  in_sheet_not_found = set(new_cn.index.tolist()) - set(sample_ids)
  if len(in_sheet_not_found) > 0:
    print("We have not found " + str(len(in_sheet_not_found)) +" of the samples we're supposed to have this release:\n" + str(sorted(list(in_sheet_not_found))))
  else:
    print("We aren't missing any samples that we're supposed to have this release!")

  #
  # # goal: answer where these extra cell lines are from
  # # note: This is a very rough, quick and dirty approach. It could be easily improved.
  # print(len(sorted(list(found_unexpected))))
  # print(sorted(list(found_unexpected)))
  # for wm in wmfroms:
  #   print(str(wm))
  #   # goal: answer where these extra cell lines are from
  #   if wm == refwm:
  #     wm_samples_full = wm.get_samples()['participant'].tolist()
  #   else:
  #     wm_samples_full = wm.get_samples()['individual_alias'].tolist()
  #   wm_samples = [val[val.index('ACH'):][0:10] for val in wm_samples_full if type(val)==str and 'ACH' in val]
  #
  #   # does the number missing change?
  #   print(len(set(found_unexpected) - set(wm_samples)))
  #   print(sorted(list(set(found_unexpected) - set(wm_samples))))
  #   print("\n")
  #
  # # these are the lines we have set to process that aren't in Emily's list of lines we expect
  # found_unexpected = set(sample_ids) - set(new_cn.index.tolist())
  # print("We found " + str(len(found_unexpected)) + " unexpected lines: \n" + str(found_unexpected))
  #
  # print("The following can be used to start figuring out where these lines came from: ")
  # # goal: answer where these extra cell lines are from
  # # This is very rough, and could easily be improved. I just needed something quick and dirty.
  # wmfroms = [wm1, wm2, wm3, refwm]
  # print(sorted(list(found_unexpected)))
  # for wm in wmfroms:
  #   print(str(wm))
  #   # goal: answer where these extra cell lines are from
  #   if wm == refwm:
  #     wm_samples_full = wm.get_samples()['participant'].tolist()
  #   else:
  #     wm_samples_full = wm.get_samples()['individual_alias'].tolist()
  #   wm_samples = [val[val.index('ACH'):][0:10] for val in wm_samples_full if type(val)==str and 'ACH' in val]
  #
  #   # does the number missing change?
  #   print(len(set(found_unexpected) - set(wm_samples)))
  #   print(sorted(list(set(found_unexpected) - set(wm_samples))))
