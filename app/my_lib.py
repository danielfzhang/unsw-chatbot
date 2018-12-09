import requests, re, nltk, json, os, threading
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import linear_kernel
from googleapiclient.discovery import build
from datetime import date, datetime
from bson.objectid import ObjectId
from bs4 import BeautifulSoup
from app import mongo

if "data" not in vars():
    #external engine api
    developerKey = os.environ.get('developerKey', None)
    cx = os.environ.get('cx', None)
    service = None
    if developerKey and cx:
        service = build("customsearch", "v1", developerKey=developerKey)

    #cache asked questions for improving performance
    cache = {}

    #read key, subkey, synonyms list, etc. locally
    with open('app/data.json', encoding="utf-8") as f:
        data = json.load(f)
    with open('app/qa.json', encoding="utf-8") as f:
        key_id_list = json.load(f)

    db_keys = data['keys']
    db_subkeys = data['subkeys']
    inversed_unsw_voc = data['inversed_unsw_voc']
    unsw_vocabulary = data['unsw_vocabulary']
    corpus_vocabulary = data['corpus_vocabulary']

def update_qa():
    '''
    update local qa searchkeys. delete old one, download new one from
    mongodb and store it locally. 
    This function aims to be called manually.
    '''
    global key_id_list
    if os.path.exists('app/qa.json'):
        os.remove('app/qa.json')
    faq = list(mongo.db.qa.find({},{"searchkey":1}))
    key_id_list['key'] = []
    key_id_list['id'] = []
    for f in faq:
        key_id_list['id'] += [str(f['_id'])]
        key_id_list['key'] += [f['searchkey']]
    with open('app/qa.json', 'w') as outfile:
        json.dump(key_id_list, outfile)

def synonymize(sentence, vocabulary):
    '''
    use vocabulary list to replace the words in sentence.
    '''
    for k, v in vocabulary.items():
        start = sentence.find(k)
        #ensure it is one word
        if start == 0 or (start > 0 and sentence[start-1] == ' '):
            end = start + len(k)
            if end == len(sentence) or sentence[end] == ' ':
                sentence = sentence.replace(k, v)
    return sentence

def get_timetable(nomarlized_q):
    '''
    grab timetable if there is "timetable" and "semester 1/2/3" in the query.
    return url and timetable
    otherwise return None, None
    '''
    if "timet" not in nomarlized_q and "time tabl" not in nomarlized_q:
        return None,  None
    coursecode = re.search("(^| )[a-z][a-z][a-z][a-z]\d\d\d\d( |$)", nomarlized_q)
    if coursecode is None:
        return None, None

    codeindex = coursecode.span()
    coursecode = nomarlized_q[codeindex[0]:codeindex[1]].strip()
    coursecode = "".join(coursecode.split())

    if 't1' in nomarlized_q or 'semest one' in nomarlized_q or 'semest 1' in nomarlized_q or 'term one' in nomarlized_q or 'term 1' in nomarlized_q or 'term1' in nomarlized_q:
        return courseTimeTable(coursecode, 't1')
    elif 't2' in nomarlized_q or 'semest two' in nomarlized_q or 'semest 2' in nomarlized_q or 'term two' in nomarlized_q or 'term 2' in nomarlized_q or 'term2' in nomarlized_q:
        return courseTimeTable(coursecode, 't2')
    elif 't3' in nomarlized_q or 'semest three' in nomarlized_q or 'semest 3' in nomarlized_q or 'term three' in nomarlized_q or 'term 3' in nomarlized_q or 'term3' in nomarlized_q:
        return courseTimeTable(coursecode, 't3')
    else:
        return None, None

def courseTimeTable(course_code, semester):
    course_code = course_code.upper()

    if semester == 't1':
        period = 'Teaching Period One'
    elif semester == 't2':
        period = 'Teaching Period Two'
    else:
        period = 'Teaching Period Three'

    url = 'http://timetable.unsw.edu.au/{}/{}.html'
    next_year = date.today().year + 1

    for i in range(2):
        timetable_url = url.format(str(next_year - i),course_code)
        try:
            response = requests.get(timetable_url)
        except:
            print("Do not find timetable of {}".format(course_code))

        soup = BeautifulSoup(response.text, "html.parser")
        if soup.find(text = re.compile('timetable information for the selected course was not found')):
            continue
        try:
            result = soup.find(text = period).parent
            while result.name != "table":
                result = result.parent
            result = str(result.find_next_sibling("table"))
            result = result.replace("href=\"#","href=\"{}#".format(timetable_url))
            return timetable_url, result
        except:
            pass
    return None, "Do not find {} time table for {}".format(period.lower(), course_code)
    
def normalize_sentence(orig_str):
    wnl = nltk.WordNetLemmatizer()
    porter = nltk.PorterStemmer()

    #case folding
    orig_str = orig_str.lower()
    #remove stop words
    orig_str = " ".join([o for o in orig_str.split() if o not in ['tell', 'can', 'about']])
    #normarlize course code
    coursecode = re.search("(^| )[a-z][a-z][a-z][a-z]\s+\d\d\d\d( |$)", orig_str)
    if coursecode:
        old_code = coursecode.group(0).strip()
        new_code = "".join(old_code.split())
        orig_str = orig_str.replace(old_code, new_code)

    orig_str = orig_str.replace('/',' ')
    #Tokenization
    tokens = nltk.word_tokenize(orig_str)
    #Stemming
    tokens = [porter.stem(tk) for tk in tokens]
    #Stemming of are,am,is
    tokens = [re.sub("('|`)(s|re|m)",'be', tk) for tk in tokens]
    #Lemmatization
    tokens = [wnl.lemmatize(tk) for tk in tokens]
    #Remove punctuation
    punctuation = '!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'
    tokens = [tk for tk in tokens if tk not in punctuation]

    return " ".join(tokens)

def write_to_mongo(raw_question, key):
    try:
        mongo.db.recording.insert_one({'question':raw_question,'key':key})
        print('______ wrote to mongo ______')
    except:
        print('______ had this recording in db ______')

def acronymize_translate(nomarlized_q):
    tokens = nomarlized_q.split()
    tokens = [corpus_vocabulary.get(tk,tk) for tk in tokens]
    return " ".join(tokens)

def chatbot_answers(raw_question):
    # "<$s$>" is special characters used to 
    # separate question and the key from last answer
    split_q = raw_question.split("<$s$>")
    last_key = ""
    if len(split_q) > 1:
        raw_question = split_q[0]
        last_key = split_q[1]

    #if question contains it, that, this
    #add the key from last answer into question
    nomarlized_q = normalize_sentence(raw_question)
    for k in ['it', 'that', 'thi']:
        if k in nomarlized_q.split():
            nomarlized_q += " " + last_key
            break
    nomarlized_q = nomarlized_q.strip()
    print("="*16)
    print("raw_q:" + raw_question)
    print("normarlized_q: " + nomarlized_q)

    #answer form cache
    if nomarlized_q in cache:
        print("cached question\n" + "*"*16)
        return cache[nomarlized_q]
 
    #real-time timetable
    timetable_url, timetable = get_timetable(nomarlized_q)
    if timetable:
        if timetable_url:
            print(timetable_url)
            print("*"*16)
            return timetable + "<$s$>" + timetable_url[-13:-5].lower()
        else:
            print(timetable)
            print("*"*16)
            return timetable + "<$s$>" + timetable[-8:].lower()

    #attribute from unsw collection
    unsw_q = synonymize(nomarlized_q, unsw_vocabulary)
    subkey_result, unsw_ans = extract_unsw(unsw_q)
    if unsw_ans:
        print("handbook: " + str(subkey_result) + "\n" + "*"*16)
        return unsw_ans

    #answer from FAQ collection
    copurs_q = synonymize(nomarlized_q, corpus_vocabulary)
    if copurs_q in cache:
        print("cached question\n" + "*"*16)
        return cache[copurs_q]
    else:
        searching = [copurs_q] + key_id_list['key']
        tfidf = TfidfTransformer().fit_transform(CountVectorizer().fit_transform(searching))
        cosine_similarities = linear_kernel(tfidf[0:1], tfidf[1:]).flatten()
        top1_index = cosine_similarities.argsort()[-1]
        if cosine_similarities[top1_index] >= 0.5:
            key = key_id_list['key'][top1_index]
            answer = mongo.db.qa.find_one({'_id':ObjectId(key_id_list['id'][top1_index])},{'value':1})['value']
            answer = answer[datetime.now().microsecond%len(answer)]
            key_maybe = answer.lower().split(" - ")[0][-8:]
            if key_maybe in db_keys:
                answer += "<$s$>" + key_maybe
            cache[copurs_q] = answer

            try:
                threading.Thread(target=write_to_mongo, args=(raw_question, key,)).start()
            except:
                print('threading fail')

            print("QA: "+ key +"\n" + "*"*16)
            return answer

    #answer from external engine
    if service:
        response = service.cse().list(q=raw_question, cx=cx, num=1).execute()
        if 'items' in list(response):
            answer = "<a href=\"{}\">{}</a><br/>{}".format(response['items'][0]['link'],response['items'][0]['title'],response['items'][0]['snippet'])
            cache[nomarlized_q] = answer

            try:
                threading.Thread(target=write_to_mongo, args=(raw_question, "external engine",)).start()
            except:
                print('threading fail')

            print("external engine\n" + "*"*16)
            return answer

    try:
        threading.Thread(target=write_to_mongo, args=(raw_question, "None",)).start()
    except:
        print('threading fail')

    return "I will seriously think about this question and hope to answer you next time."

def extract_unsw(nomarlized_q):

    tks = nomarlized_q.split()

    gram5 = []
    for i in range(1,6):
        for j in range(0,len(tks)-i+1):
            gram5 += [" ".join(tks[j:j+i])]

    found_keys = [n for n in gram5 if n in db_keys]
    found_subkeys = [n for n in gram5 if n in db_subkeys]

    if len(found_keys) == 0 or len(found_subkeys) == 0:
        return None, None
    match_list = []
    project_dic = {'_id':0, 'key':1, 'type':1, 'level':1}

    for s in found_subkeys:
        project_dic[s] = 1
        for k in found_keys:
            match_list += [{"key":k, s:{ "$exists": True}}]

    db_result = list(mongo.db.unsw1.aggregate([{'$match':{'$or':match_list}},{'$project':project_dic}]))

    if db_result:
        result = ""
        for k in found_keys:
            s_result = []
            d_result = []
            for s in found_subkeys:
                for d in db_result:
                    if k in d['key'] and s in d.keys():
                        if len(d[s]) > 350:
                            return s ,d[s]+"<$s$>"+found_keys[0]
                        s_result += [s]
                        d_result += [d[s]]
            s_result = list(set(s_result))#remove suplicated results
            d_result = list(set(d_result))#remove suplicated results


            s_result = [inversed_unsw_voc.get(s,s) for s in s_result]

            if s_result and d_result:
                s_str = s_result[0]
                if len(s_result) == 2:
                    s_str = ", and ".join(s_result)
                else:
                    s_str = ", ".join(s_result[:-1])
                    s_str = ", and ".join([s_str, s_result[-1]])
                s_str = re.sub('^, and ','', s_str)

                d_str = d_result[0]
                if len(d_result) == 2:
                    d_str = ", and ".join(d_result)
                else:
                    d_str = ", ".join(d_result[:-1])
                    d_str = ", and ".join([d_str, d_result[-1]])
                d_str = re.sub('^, and ','', d_str)

                result += '<br>It is {}.'.format(d_str)

        result = result[4:]

        return s_result, result+"<$s$>"+found_keys[0]
    else:
        return None, None

