/*
 * Wiki Handling Tool
 *
 * Copyright (C) 2008 Openmoko Inc.
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include "CreateIndex.h"
#include "CreateText.h"
#include "ExtractWords.h"
#include "ExtractText.h"
#include "ExtractTextCompressed.h"
#include "ExtractTextHashed.h"
#include "ExtractTitles.h"
#include "SplitArticles.h"

#include "StreamReader.h"

#include <QCoreApplication>
#include <QRegExp>

static void setupHandlers(QList<ArticleHandler*>* handlers, int, char**)
{
    // Enable that if you want to create an index
    // *handlers << new CreateIndex(QLatin1String(" "), 
    //                              QLatin1String("indexfile.index"), 
    //                              QLatin1String("notmatch.title"), 
    //                              QRegExp("(^Image:.*)|(^Category:.*)|(^Talk:.*)|(^Template:.*)|(^Wikipedia:.*)|(^Special:.*)") ,
    //                              QRegExp("[0-9A-Za-z\\s\\.]*") );

    // Some example runs... take a look
    //*handlers << new CreateText(QString());
    //*handlers << new ExtractTitles(QString("extracted.titles"));
    //*handlers << new ExtractWords(QString());
    //*handlers << new ExtractText(QString("extracted.text"));

    // Enable that if you want to write out compressed text
    //*handlers << new ExtractTextCompressed(QString("extracted.text.1.bz2"), Compression::Method_Bzip2, 1);
    //*handlers << new ExtractTextCompressed(QString("extracted.text.4.bz2"), Compression::Method_Bzip2, 4);
    //*handlers << new ExtractTextCompressed(QString("extracted.text.9.bz2"), Compression::Method_Bzip2, 9);

    //*handlers << new ExtractTextCompressed(QString("extracted.text.1.gz"), Compression::Method_Zlib, 1);
    //*handlers << new ExtractTextCompressed(QString("extracted.text.4.gz"), Compression::Method_Zlib, 4);
    //*handlers << new ExtractTextCompressed(QString("extracted.text.9.gz"), Compression::Method_Zlib, 9);

    // Enable that if you want to split articles
    //*handlers << new SplitArticles(50, QString("split_enwiki"));

    // Enable that if you want to split the articles into a hash structur
    //*handlers << new ExtractTextHashed(QString("articles"));
}

#define INVOKE_HANDLERS(function)               \
    foreach(ArticleHandler* handler, handlers)  \
        handler->function;

int main(int argc, char** argv)
{
    QCoreApplication app(argc, argv);

    QList<ArticleHandler*> handlers;
    StreamReader reader;

    QFile file;
    if (!file.open(STDIN_FILENO, QFile::ReadOnly)) {
        fprintf(stderr, "Failed to open stdin\n");
        return EXIT_FAILURE;
    }

    setupHandlers(&handlers, argc, argv);

    INVOKE_HANDLERS(parsingStarts())

    unsigned long long article_count = 0;

    do {
        if ((++article_count % 1000) == 0)
            printf("Handled another 1000 articles. Now: %lld\n", article_count);

        // Write whatever is available
        file.waitForReadyRead(-1);
        reader.write(file.read(file.bytesAvailable()));

        // Did we finish parsing an article?
        QList<Article> articles = reader.popArticles();
        foreach(ArticleHandler* handler, handlers)
            foreach(Article article, articles)
                handler->handleArticle(article);
    } while (!reader.finished());

    INVOKE_HANDLERS(parsingFinished())
}
