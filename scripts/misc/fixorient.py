#!/usr/bin/env python

import sys
import os
import subprocess
import logging
import argparse

#import align
import pysam
import numpy as np

from uuid import uuid4


FORMAT = '%(asctime)s %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def rc(dna):
    ''' reverse complement '''
    complements = maketrans('acgtrymkbdhvACGTRYMKBDHV', 'tgcayrkmvhdbTGCAYRKMVHDB')
    return dna.translate(complements)[::-1]


def align(qryseq, refseq, elt='PAIR', minmatch=90.0):
    rnd = str(uuid4())
    tgtfa = 'tmp.' + rnd + '.tgt.fa'
    qryfa = 'tmp.' + rnd + '.qry.fa'

    tgt = open(tgtfa, 'w')
    qry = open(qryfa, 'w')

    tgt.write('>ref' + '\n' + refseq + '\n')
    qry.write('>qry' + '\n' + qryseq + '\n')

    tgt.close()
    qry.close()

    cmd = ['exonerate', '--bestn', '1', '-m', 'ungapped', '--showalignment','0', '--ryo', elt + '\t%s\t%qab\t%qae\t%tab\t%tae\t%pi\t%qS\t%tS\n', qryfa, tgtfa]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    best = []
    topscore = 0

    for pline in p.stdout.readlines():
        if pline.startswith(elt):
            c = pline.strip().split()
            if int(c[1]) > topscore and float(c[6]) >= minmatch:
                topscore = int(c[1])
                best = c

    os.remove(tgtfa)
    os.remove(qryfa)

    return best


def flip_ends(rec):
    rec['5_Prime_End'], rec['3_Prime_End'] = rec['3_Prime_End'], rec['5_Prime_End']
    rec['Orient_5p'], rec['Orient_3p'] = rec['Orient_3p'], rec['Orient_5p']
    rec['5p_Elt_Match'], rec['3p_Elt_Match'] = rec['3p_Elt_Match'], rec['5p_Elt_Match']
    rec['5p_Genome_Match'], rec['3p_Genome_Match'] = rec['3p_Genome_Match'], rec['5p_Genome_Match']
    rec['Split_reads_5prime'], rec['Split_reads_3prime'] = rec['Split_reads_3prime'], rec['Split_reads_5prime']
    rec['5p_Cons_Len'], rec['3p_Cons_Len'] = rec['3p_Cons_Len'], rec['5p_Cons_Len']
    rec['5p_Improved'], rec['3p_Improved'] = rec['3p_Improved'], rec['5p_Improved']
    rec['TSD_3prime'], rec['TSD_5prime'] = rec['TSD_5prime'], rec['TSD_3prime']
    rec['Genomic_Consensus_5p'], rec['Genomic_Consensus_3p'] = rec['Genomic_Consensus_3p'], rec['Genomic_Consensus_5p']
    rec['Insert_Consensus_5p'], rec['Insert_Consensus_3p'] = rec['Insert_Consensus_3p'], rec['Insert_Consensus_5p']

    return rec


def load_falib(infa):
    seqdict = {}

    with open(infa, 'r') as fa:
        seqid = ''
        seq   = ''
        for line in fa:
            if line.startswith('>'):
                if seq != '':
                    seqdict[seqid] = seq
                seqid = line.lstrip('>').strip().split()[0]
                seq   = ''
            else:
                assert seqid != ''
                seq = seq + line.strip()

    if seqid not in seqdict and seq != '':
        seqdict[seqid] = seq

    return seqdict


def fix_ins_id(ins_id, inslib):
    superfam, subfam = ins_id.split(':')

    for i in inslib.keys():
        if i.split(':')[-1] == subfam:
            superfam = i.split(':')[0]

    return '%s:%s' % (superfam, subfam)


def main(args):

    inslib = None

    if args.insref:
        inslib = load_falib(args.insref)

    ref = pysam.Fastafile(args.refgenome)

    header = []

    count_5p_diff = 0
    count_3p_diff = 0
    count_5p_switchcons = 0
    count_3p_switchcons = 0

    with open(args.table, 'r') as table:
        for i, line in enumerate(table):
            if i == 0:
                header = line.strip().split('\t')
                print line.strip()

            else:
                rec = {}

                for n, field in enumerate(line.strip().split('\t')):
                    rec[header[n]] = field

                ins_id = '%s:%s' % (rec['Superfamily'], rec['Subfamily'])

                if rec['Superfamily'] == 'NA':
                    ins_id = rec['Subfamily']

                if rec['Subfamily'] == 'NA':
                    ins_id = rec['Superfamily']

                if ins_id not in inslib:
                    ins_id = fix_ins_id(ins_id, inslib)

                    if ins_id not in inslib:
                        logger.warn('No insertion identification for %s (ins_id %s)' % (rec['UUID'], ins_id))
                        continue

                refseq = ref.fetch(rec['Chromosome'], int(rec['Left_Extreme']), int(rec['Right_Extreme']))

                #print rec['Genomic_Consensus_5p'], inslib[ins_id]
                elt_5p_align = align(rec['Genomic_Consensus_5p'], inslib[ins_id])
                elt_3p_align = align(rec['Genomic_Consensus_3p'], inslib[ins_id])
                gen_5p_align = align(rec['Genomic_Consensus_5p'], refseq)
                gen_3p_align = align(rec['Genomic_Consensus_3p'], refseq)

                # try using the insertion-based consensus if no luck with the genomic one

                if not elt_5p_align or not gen_5p_align:
                    retry_elt_5p_align = align(rec['Insert_Consensus_5p'], inslib[ins_id])
                    retry_gen_5p_align = align(rec['Insert_Consensus_5p'], refseq)

                    if retry_gen_5p_align and retry_elt_5p_align:
                        elt_5p_align = retry_elt_5p_align
                        gen_5p_align = retry_gen_5p_align
                        count_5p_switchcons += 1


                if not elt_3p_align or not gen_3p_align:
                    retry_elt_3p_align = align(rec['Insert_Consensus_3p'], inslib[ins_id])
                    retry_gen_3p_align = align(rec['Insert_Consensus_3p'], refseq)

                    if retry_gen_3p_align and retry_elt_3p_align:
                        elt_3p_align = retry_elt_3p_align
                        gen_3p_align = retry_gen_3p_align
                        count_3p_switchcons += 1

                elt_5p_orient = 'NA'
                elt_3p_orient = 'NA'
                gen_5p_orient = 'NA'
                gen_3p_orient = 'NA'

                if elt_5p_align:
                    elt_5p_orient = elt_5p_align[-1]

                if elt_3p_align:
                    elt_3p_orient = elt_3p_align[-1]

                if gen_5p_align:
                    gen_5p_orient = gen_5p_align[-1]

                if gen_3p_align:
                    gen_3p_orient = gen_3p_align[-1]

                new_5p_orient = 'NA'
                new_3p_orient = 'NA'

                if 'NA' not in (elt_5p_orient, gen_5p_orient):
                    if elt_5p_orient == gen_5p_orient:
                        new_5p_orient = '+'
                    else:
                        new_5p_orient = '-'

                if 'NA' not in (elt_3p_orient, gen_3p_orient):
                    if elt_3p_orient == gen_3p_orient:
                        new_3p_orient = '+'
                    else:
                        new_3p_orient = '-'

                coords_5p = []
                coords_3p = []

                if elt_5p_align:
                    coords_5p = sorted(map(int, (elt_5p_align[4], elt_5p_align[5])))

                if elt_3p_align:
                    coords_3p = sorted(map(int, (elt_3p_align[4], elt_3p_align[5])))

                flip = False
                if coords_5p and coords_3p and coords_5p[1] > coords_3p[1]:
                    flip = True

                if rec['Orient_5p'] != new_5p_orient:
                    logger.info('Changed 5p orientation for %s' % rec['UUID'])

                if rec['Orient_3p'] != new_3p_orient:
                    logger.info('Changed 3p orientation for %s' % rec['UUID'])

                rec['Orient_5p'] = new_5p_orient
                rec['Orient_3p'] = new_3p_orient

                if 'NA' not in (new_5p_orient, new_3p_orient) and 'None' not in (rec['Orient_5p'], rec['Orient_3p']):
                    if rec['Orient_5p'] != rec['Orient_3p']:
                        rec['Inversion'] = 'Y'
                    else:
                        rec['Inversion'] = 'N'

                else:
                    rec['Inversion'] = 'N'


                if flip:
                    rec = flip_ends(rec)

                out = [rec[h] for h in header]

                print '\t'.join(out)
                
    logger.info('Changed orientation on %d 5p ends' % count_5p_diff)
    logger.info('Changed orientation on %d 3p ends' % count_3p_diff)
    logger.info('Used insertion consensus for %d 5p ends' % count_5p_switchcons)
    logger.info('Used insertion consensus for %d 3p ends' % count_3p_switchcons)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='foo')
    parser.add_argument('-t', '--table', required=True, help='tabular output from resolve.py, requires header to be present')
    parser.add_argument('-i', '--insref', required=True, help='insertion sequence reference')
    parser.add_argument('-r', '--refgenome', required=True, help='reference genome')
    args = parser.parse_args()
    main(args)
