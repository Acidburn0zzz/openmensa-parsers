#!python3
from urllib.request import urlopen
from urllib.parse import urlencode
from bs4 import BeautifulSoup as parse
import re
import datetime

from pyopenmensa.feed import OpenMensaCanteen

day_regex = re.compile('(?P<date>\d{2}\. ?\d{2}\. ?\d{4})')
day_range_regex = re.compile('(?P<from>\d{2}\.\d{2}).* (?P<to>\d{2}\.\d{2}\.(?P<year>\d{4}))')
price_regex = re.compile('(?P<price>\d+[,.]\d{2}) ?€')
extra_regex = re.compile('\((?P<extra>[0-9,]+)\)')
legend_regex = re.compile('\((\d+)\) (\w+(\s|\w)*)')


def parse_week(url, data, canteen):
    document = parse(urlopen(url, data).read())
    # parse extra/notes legend
    legends = {}
    legendsData = document.find('table', 'zusatz_std')
    if legendsData:
        legends = {int(v[0]): v[1] for v in legend_regex.findall(legendsData.text.replace('\xa0', ' '))}
    data = document.find('table', 'wo_std')
    if not data:
        message = document.find('div', 'Meldung_std')
        if message:
            m = day_range_regex.search(message.text)
            if m:
                fromDate = datetime.datetime.strptime(m.group('from') + '.' + m.group('year'), '%d.%m.%Y')
                toDate = datetime.datetime.strptime(m.group('to'), '%d.%m.%Y')
                while fromDate <= toDate:
                    canteen.setDayClosed(fromDate.strftime('%Y-%m-%d'))
                    fromDate += datetime.date.resolution
        return
    # iterator about all rows of the table
    rowIter = iter(document.find('table', 'wo_std').find_all('tr'))
    # extra category names from th's of first row
    headRow = next(rowIter)
    for br in headRow.find_all('br'):
        br.replace_with(document.new_string(' - '))

    categories = list()
    for aHeadRow in headRow.find_all('th')[1:]:
        aCategory = aHeadRow.text.strip()
        if aCategory[-2:] == ' -':
            aCategory = aCategory[:-2]

        if aCategory == '-':
            categories.append('Spezialmenü')
        else:
            categories.append(aCategory)

    try:
        while True:
            tr = next(rowIter)  # meal row
            # extract date from first column:
            date = day_regex.search(tr.contents[0].text).group('date')
            if tr.contents[0].get('rowspan') is None:
                canteen.setDayClosed(date)
                continue

            # extract information from addition meal component row
            extratr = next(rowIter)
            extras = extratr.text.replace('\xa0', ' ').replace('  ', ' ').strip().split(' – ');

            # build iterators for lists:
            categoriesIterator = iter(categories)
            colIter = iter(tr.find_all('td'))
            extraIter = iter(extratr.find_all('td'))
            # skip first row (date):
            next(colIter)
            next(extraIter)

            # add meals
            try:
                while True:
                    category = next(categoriesIterator)
                    mainMeals = next(colIter).text.split(' oder ')
                    price = next(colIter).text
                    if price.strip() == '€':  # no real price available
                        price = None

                    for aMainMeal in mainMeals:
                        # extract notes from name
                        notes = [legends[int(v)] for v in set(','.join(extra_regex.findall(aMainMeal)).split(',')) if v and int(v) in legends]
                        # remove notes from name
                        aMainMeal = extra_regex.sub('', aMainMeal).replace('\xa0', ' ').replace('  ', ' ').strip()
                        # add meal
                        canteen.addMeal(date, category, aMainMeal, notes, price)
            except StopIteration:
                pass

            if len(extras) >= 1:
                mainExtras = extras[0].replace('Hauptbeilage: ', ' ').split(' oder ')
                # add main extra
                try:
                    for aMainExtra in mainExtras:
                        # extract notes from name
                        notes = [legends[int(v)] for v in set(','.join(extra_regex.findall(aMainExtra)).split(',')) if v and int(v) in legends]
                        # remove notes from name
                        aMainExtra = extra_regex.sub('', aMainExtra).replace('\xa0', ' ').replace('  ', ' ').strip()
                        # add extra
                        canteen.addMeal(date, 'Hauptbeilagen', aMainExtra, notes)
                except StopIteration:
                    pass

            if len(extras) >= 2:
                sideExtras = extras[1].replace('Gemüse/Salat: ', ' ').split(' oder ')
                # add side extra
                try:
                    for aSideExtra in sideExtras:
                        # extract notes from name
                        notes = [legends[int(v)] for v in set(','.join(extra_regex.findall(aSideExtra)).split(',')) if v and int(v) in legends]
                        # remove notes from name
                        aSideExtra = extra_regex.sub('', aSideExtra).replace('\xa0', ' ').replace('  ', ' ').strip()
                        # add extra
                        canteen.addMeal(date, 'Gemüse/Salat', aSideExtra, notes)
                except StopIteration:
                    pass
    except StopIteration:
        pass


def parse_url(url, today=False):
    canteen = OpenMensaCanteen()
    canteen.setAdditionalCharges('student', {'other': 1.5})
    document = parse(urlopen(url).read())
    for submit in document.find_all('input'):
        if submit['type'] != 'submit':
            continue
        parse_week(url, urlencode({submit['name']: submit['value']}).encode('utf8'), canteen)
        if today:
            break
    return canteen.toXMLFeed()
